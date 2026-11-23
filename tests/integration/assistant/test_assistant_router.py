import json
from collections.abc import AsyncGenerator, AsyncIterator
from typing import Any
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import settings
from infra.database.session import get_db
from main import app
from modules.assistant.domain.entities.knowledge_chunk import KnowledgeChunk
from modules.assistant.domain.entities.llm_events import LLMStreamEvent, ToolCallRequest
from modules.assistant.infra.gemini.provider_factory import (
    get_embedding_provider,
    get_llm_provider,
)
from modules.assistant.infra.repositories.knowledge_sqlalchemy_repository import (
    KnowledgeSQLAlchemyRepository,
)
from security.jwt import create_access_token
from security.rate_limiter import limiter
from shared.enums.user_role import UserRole
from tests.factories.tenant_factory import TenantFactory
from tests.factories.user_factory import UserFactory


def _unit_vector(hot_index: int = 0, dims: int = 768) -> list[float]:
    vec = [0.0] * dims
    vec[hot_index] = 1.0
    return vec


class FakeEmbeddingProvider:
    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [_unit_vector(0) for _ in texts]

    async def embed_query(self, text: str) -> list[float]:
        return _unit_vector(0)


class FakeLLMProvider:
    def __init__(self, turns: list[list[LLMStreamEvent]]) -> None:
        self._turns = list(turns)

    @property
    def model_name(self) -> str:
        return "fake-gemini-2.5-flash"

    async def stream_turn(
        self,
        *,
        system_prompt: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> AsyncIterator[LLMStreamEvent]:
        events = self._turns.pop(0) if self._turns else []
        for event in events:
            yield event


def _parse_sse_frames(raw_body: str) -> list[tuple[str, dict[str, Any]]]:
    frames: list[tuple[str, dict[str, Any]]] = []
    for block in raw_body.strip().split("\n\n"):
        if not block.strip():
            continue
        event_name = "message"
        data_json = "{}"
        for line in block.splitlines():
            if line.startswith("event:"):
                event_name = line.removeprefix("event:").strip()
            elif line.startswith("data:"):
                data_json = line.removeprefix("data:").strip()
        frames.append((event_name, json.loads(data_json)))
    return frames


@pytest.fixture
async def client(session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield session

    app.dependency_overrides[get_db] = override_get_db
    limiter.enabled = False
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            yield ac
    finally:
        limiter.enabled = True
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_llm_provider, None)
        app.dependency_overrides.pop(get_embedding_provider, None)


class TestAssistantRouter:
    async def test_unauthenticated_returns_401_and_student_returns_403(
        self,
        client: AsyncClient,
        session: AsyncSession,
    ) -> None:
        # Sem token -> 401
        unauth_res = await client.get("/assistant/conversations")
        assert unauth_res.status_code == 401

        # Papel ALUNO -> 403
        student = await UserFactory.create(session)
        tenant = await TenantFactory.create(session)
        await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=student.id, role=UserRole.ALUNO
        )
        student_token = create_access_token(
            user_id=student.id,
            tenant_id=tenant.id,
            role=UserRole.ALUNO.value,
        )
        student_res = await client.post(
            "/assistant/conversations",
            headers={"Authorization": f"Bearer {student_token}"},
        )
        assert student_res.status_code == 403

    async def test_conversation_crud_and_cross_user_tenant_isolation(
        self,
        client: AsyncClient,
        session: AsyncSession,
    ) -> None:
        tenant_a = await TenantFactory.create(session)
        tenant_b = await TenantFactory.create(session)
        prof = await UserFactory.create(session)
        other_user = await UserFactory.create(session)

        await TenantFactory.create_member(
            session, tenant_id=tenant_a.id, user_id=prof.id, role=UserRole.PROFESSOR
        )
        await TenantFactory.create_member(
            session, tenant_id=tenant_a.id, user_id=other_user.id, role=UserRole.ADMIN
        )

        prof_token = create_access_token(
            user_id=prof.id, tenant_id=tenant_a.id, role=UserRole.PROFESSOR.value
        )
        other_user_token = create_access_token(
            user_id=other_user.id, tenant_id=tenant_a.id, role=UserRole.ADMIN.value
        )
        prof_other_tenant_token = create_access_token(
            user_id=prof.id, tenant_id=tenant_b.id, role=UserRole.PROFESSOR.value
        )

        # Cria conversa
        create_res = await client.post(
            "/assistant/conversations",
            json={"title": "Dúvida sobre chamadas"},
            headers={"Authorization": f"Bearer {prof_token}"},
        )
        assert create_res.status_code == 201
        conv_id = create_res.json()["id"]
        assert create_res.json()["title"] == "Dúvida sobre chamadas"

        # Lista conversas do próprio usuário
        list_res = await client.get(
            "/assistant/conversations",
            headers={"Authorization": f"Bearer {prof_token}"},
        )
        assert list_res.status_code == 200
        assert len(list_res.json()) == 1
        assert list_res.json()[0]["id"] == conv_id

        # Outro usuário na mesma tenant recebe 404 ao tentar acessar ou deletar
        foreign_get = await client.get(
            f"/assistant/conversations/{conv_id}",
            headers={"Authorization": f"Bearer {other_user_token}"},
        )
        assert foreign_get.status_code == 404

        foreign_del = await client.delete(
            f"/assistant/conversations/{conv_id}",
            headers={"Authorization": f"Bearer {other_user_token}"},
        )
        assert foreign_del.status_code == 404

        # Mesmo usuário em outra tenant recebe 404
        cross_tenant_get = await client.get(
            f"/assistant/conversations/{conv_id}",
            headers={"Authorization": f"Bearer {prof_other_tenant_token}"},
        )
        assert cross_tenant_get.status_code == 404

        # Dono deleta com sucesso -> 204
        del_res = await client.delete(
            f"/assistant/conversations/{conv_id}",
            headers={"Authorization": f"Bearer {prof_token}"},
        )
        assert del_res.status_code == 204

        get_after_del = await client.get(
            f"/assistant/conversations/{conv_id}",
            headers={"Authorization": f"Bearer {prof_token}"},
        )
        assert get_after_del.status_code == 404

    async def test_missing_gemini_api_key_returns_503_with_clear_pt_br_message(
        self,
        client: AsyncClient,
        session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(settings, "gemini_api_key", "")

        tenant = await TenantFactory.create(session)
        admin = await UserFactory.create(session)
        await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=admin.id, role=UserRole.ADMIN
        )
        token = create_access_token(
            user_id=admin.id, tenant_id=tenant.id, role=UserRole.ADMIN.value
        )
        headers = {"Authorization": f"Bearer {token}"}

        create_res = await client.post("/assistant/conversations", headers=headers)
        conv_id = create_res.json()["id"]

        msg_res = await client.post(
            f"/assistant/conversations/{conv_id}/messages",
            json={"content": "Como abrir uma chamada?"},
            headers=headers,
        )
        assert msg_res.status_code == 503
        assert "GEMINI_API_KEY" in msg_res.json()["detail"]

    async def test_sse_endpoint_streams_status_delta_done_and_persists_messages(
        self,
        client: AsyncClient,
        session: AsyncSession,
    ) -> None:
        tenant = await TenantFactory.create(session)
        coord = await UserFactory.create(session)
        await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=coord.id, role=UserRole.COORDENADOR
        )
        token = create_access_token(
            user_id=coord.id, tenant_id=tenant.id, role=UserRole.COORDENADOR.value
        )
        headers = {"Authorization": f"Bearer {token}"}

        # Popula 1 chunk real no banco para ser retornado pela tool search_locus_docs
        knowledge_repo = KnowledgeSQLAlchemyRepository(session=session)
        await knowledge_repo.upsert_chunks(
            [
                KnowledgeChunk(
                    id=uuid4(),
                    doc_slug="04-chamadas-ao-vivo",
                    section_title="Chamadas ao Vivo > Como abrir uma chamada",
                    content="Acesse /dashboard/chamadas/nova para iniciar uma chamada ao vivo.",
                    routes=["/dashboard/chamadas/nova"],
                    allowed_roles=["ALL"],
                    content_hash="hash-sse-test",
                    embedding=_unit_vector(0),
                )
            ]
        )

        fake_llm = FakeLLMProvider(
            turns=[
                [
                    LLMStreamEvent(
                        kind="tool_call",
                        tool_call=ToolCallRequest(
                            name="search_locus_docs",
                            arguments={"query": "abrir chamada"},
                        ),
                    ),
                    LLMStreamEvent(kind="usage", tokens_in=90, tokens_out=10),
                ],
                [
                    LLMStreamEvent(
                        kind="delta",
                        text="Para abrir uma chamada, acesse `/dashboard/chamadas/nova`.",
                    ),
                    LLMStreamEvent(kind="usage", tokens_in=200, tokens_out=25),
                ],
            ]
        )
        app.dependency_overrides[get_llm_provider] = lambda: fake_llm
        app.dependency_overrides[get_embedding_provider] = lambda: FakeEmbeddingProvider()

        create_res = await client.post("/assistant/conversations", headers=headers)
        conv_id = create_res.json()["id"]

        stream_res = await client.post(
            f"/assistant/conversations/{conv_id}/messages",
            json={
                "content": "Como abrir uma chamada?",
                "current_route": "/dashboard",
            },
            headers=headers,
        )
        assert stream_res.status_code == 200
        assert stream_res.headers["content-type"].startswith("text/event-stream")
        assert stream_res.headers["cache-control"] == "no-cache"
        assert stream_res.headers["x-accel-buffering"] == "no"

        frames = _parse_sse_frames(stream_res.text)
        assert [name for name, _ in frames] == ["status", "delta", "done"]
        assert frames[0][1]["stage"] == "searching_docs"
        assert frames[0][1]["query"] == "abrir chamada"
        assert frames[1][1] == {
            "text": "Para abrir uma chamada, acesse `/dashboard/chamadas/nova`."
        }
        assert frames[2][1]["sources"] == [
            {
                "doc_slug": "04-chamadas-ao-vivo",
                "section_title": "Chamadas ao Vivo > Como abrir uma chamada",
                "routes": ["/dashboard/chamadas/nova"],
            }
        ]

        # Verifica persistência no banco via GET /assistant/conversations/{id}
        detail_res = await client.get(
            f"/assistant/conversations/{conv_id}",
            headers=headers,
        )
        assert detail_res.status_code == 200
        detail = detail_res.json()
        assert detail["title"] == "Como abrir uma chamada?"
        assert len(detail["messages"]) == 2
        assert detail["messages"][0]["role"] == "user"
        assert detail["messages"][1]["role"] == "assistant"
        assert detail["messages"][1]["tokens_in"] == 290
        assert detail["messages"][1]["tokens_out"] == 35
        assert detail["messages"][1]["sources"][0]["doc_slug"] == "04-chamadas-ao-vivo"

        # Verifica PUT /assistant/conversations/{id}/messages/{msg_id}/feedback
        user_msg_id = detail["messages"][0]["id"]
        assistant_msg_id = detail["messages"][1]["id"]

        fb_up = await client.put(
            f"/assistant/conversations/{conv_id}/messages/{assistant_msg_id}/feedback",
            json={"rating": "up"},
            headers=headers,
        )
        assert fb_up.status_code == 200
        assert fb_up.json()["feedback_rating"] == "up"

        # GET conversa agora traz feedback_rating persistido
        detail_after = await client.get(f"/assistant/conversations/{conv_id}", headers=headers)
        assert detail_after.json()["messages"][1]["feedback_rating"] == "up"

        # Toggle off (rating: null)
        fb_clear = await client.put(
            f"/assistant/conversations/{conv_id}/messages/{assistant_msg_id}/feedback",
            json={"rating": None},
            headers=headers,
        )
        assert fb_clear.status_code == 200
        assert fb_clear.json()["feedback_rating"] is None

        # Avaliar mensagem do usuário retorna 400
        fb_user_msg = await client.put(
            f"/assistant/conversations/{conv_id}/messages/{user_msg_id}/feedback",
            json={"rating": "down"},
            headers=headers,
        )
        assert fb_user_msg.status_code == 400

        # Outro usuário na mesma tenant recebe 404
        other_user = await UserFactory.create(session)
        await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=other_user.id, role=UserRole.PROFESSOR
        )
        other_token = create_access_token(
            user_id=other_user.id,
            tenant_id=tenant.id,
            role=UserRole.PROFESSOR.value,
        )
        fb_foreign = await client.put(
            f"/assistant/conversations/{conv_id}/messages/{assistant_msg_id}/feedback",
            json={"rating": "up"},
            headers={"Authorization": f"Bearer {other_token}"},
        )
        assert fb_foreign.status_code == 404
