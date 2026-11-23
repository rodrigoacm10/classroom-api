from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from modules.assistant.application.use_cases.conversation.create_conversation import (
    CreateConversationInput,
    CreateConversationUseCase,
)
from modules.assistant.application.use_cases.conversation.delete_conversation import (
    DeleteConversationInput,
    DeleteConversationUseCase,
)
from modules.assistant.application.use_cases.conversation.get_conversation import (
    GetConversationInput,
    GetConversationUseCase,
)
from modules.assistant.application.use_cases.conversation.list_conversations import (
    ListConversationsInput,
    ListConversationsUseCase,
)
from modules.assistant.domain.entities.chat_message import ChatMessage
from modules.assistant.infra.repositories.conversation_sqlalchemy_repository import (
    ConversationSQLAlchemyRepository,
)
from shared.exceptions import ResourceNotFoundException
from tests.factories.tenant_factory import TenantFactory
from tests.factories.user_factory import UserFactory


class TestConversationRepositoryAndUseCases:
    async def test_create_get_and_persist_messages_with_observability_metadata(
        self, session: AsyncSession
    ) -> None:
        tenant = await TenantFactory.create(session)
        user = await UserFactory.create(session)
        repo = ConversationSQLAlchemyRepository(session=session)

        create_uc = CreateConversationUseCase(conversation_repo=repo)
        get_uc = GetConversationUseCase(conversation_repo=repo)

        conv = await create_uc.execute(
            CreateConversationInput(tenant_id=tenant.id, user_id=user.id)
        )
        assert conv.title == "Nova conversa"
        assert conv.tenant_id == tenant.id
        assert conv.user_id == user.id

        user_msg = await repo.add_message(
            ChatMessage(
                id=uuid4(),
                conversation_id=conv.id,
                role="user",
                content="Como abrir uma chamada ao vivo?",
            )
        )
        assistant_msg = await repo.add_message(
            ChatMessage(
                id=uuid4(),
                conversation_id=conv.id,
                role="assistant",
                content="Acesse /dashboard/chamadas/nova para iniciar a sessão.",
                sources=[
                    {
                        "doc_slug": "04-chamadas-ao-vivo",
                        "section_title": "Chamadas ao Vivo > Como abrir uma chamada",
                        "routes": ["/dashboard/chamadas/nova"],
                    }
                ],
                tool_calls_used=[
                    {"name": "search_locus_docs", "arguments": {"query": "abrir chamada"}}
                ],
                model_name="gemini-2.5-flash",
                tokens_in=412,
                tokens_out=95,
                latency_ms=840,
            )
        )

        await repo.update_title(conversation_id=conv.id, title="Como abrir uma chamada ao vivo?")

        loaded = await get_uc.execute(
            GetConversationInput(
                conversation_id=conv.id,
                tenant_id=tenant.id,
                user_id=user.id,
            )
        )
        assert loaded.title == "Como abrir uma chamada ao vivo?"
        assert len(loaded.messages) == 2
        assert loaded.messages[0].id == user_msg.id
        assert loaded.messages[0].role == "user"
        assert loaded.messages[0].content == "Como abrir uma chamada ao vivo?"

        loaded_assistant = loaded.messages[1]
        assert loaded_assistant.id == assistant_msg.id
        assert loaded_assistant.role == "assistant"
        assert loaded_assistant.sources == [
            {
                "doc_slug": "04-chamadas-ao-vivo",
                "section_title": "Chamadas ao Vivo > Como abrir uma chamada",
                "routes": ["/dashboard/chamadas/nova"],
            }
        ]
        assert loaded_assistant.tool_calls_used == [
            {"name": "search_locus_docs", "arguments": {"query": "abrir chamada"}}
        ]
        assert loaded_assistant.model_name == "gemini-2.5-flash"
        assert loaded_assistant.tokens_in == 412
        assert loaded_assistant.tokens_out == 95
        assert loaded_assistant.latency_ms == 840

    async def test_enforces_strict_tenant_and_user_isolation(self, session: AsyncSession) -> None:
        tenant_a = await TenantFactory.create(session)
        tenant_b = await TenantFactory.create(session)
        user_1 = await UserFactory.create(session)
        user_2 = await UserFactory.create(session)

        repo = ConversationSQLAlchemyRepository(session=session)
        create_uc = CreateConversationUseCase(conversation_repo=repo)
        get_uc = GetConversationUseCase(conversation_repo=repo)
        delete_uc = DeleteConversationUseCase(conversation_repo=repo)
        list_uc = ListConversationsUseCase(conversation_repo=repo)

        conv_a1 = await create_uc.execute(
            CreateConversationInput(
                tenant_id=tenant_a.id,
                user_id=user_1.id,
                title="Conversa do User 1 na Tenant A",
            )
        )

        # Outro usuário na mesma tenant não pode ler nem deletar
        with pytest.raises(ResourceNotFoundException):
            await get_uc.execute(
                GetConversationInput(
                    conversation_id=conv_a1.id,
                    tenant_id=tenant_a.id,
                    user_id=user_2.id,
                )
            )

        with pytest.raises(ResourceNotFoundException):
            await delete_uc.execute(
                DeleteConversationInput(
                    conversation_id=conv_a1.id,
                    tenant_id=tenant_a.id,
                    user_id=user_2.id,
                )
            )

        # Mesmo usuário em outra tenant não pode ler nem deletar
        with pytest.raises(ResourceNotFoundException):
            await get_uc.execute(
                GetConversationInput(
                    conversation_id=conv_a1.id,
                    tenant_id=tenant_b.id,
                    user_id=user_1.id,
                )
            )

        with pytest.raises(ResourceNotFoundException):
            await delete_uc.execute(
                DeleteConversationInput(
                    conversation_id=conv_a1.id,
                    tenant_id=tenant_b.id,
                    user_id=user_1.id,
                )
            )

        # Listagens isoladas
        assert (
            await list_uc.execute(ListConversationsInput(tenant_id=tenant_a.id, user_id=user_2.id))
            == []
        )
        assert (
            await list_uc.execute(ListConversationsInput(tenant_id=tenant_b.id, user_id=user_1.id))
            == []
        )

        # O próprio dono consegue ler e deletar
        own_list = await list_uc.execute(
            ListConversationsInput(tenant_id=tenant_a.id, user_id=user_1.id)
        )
        assert len(own_list) == 1
        assert own_list[0].id == conv_a1.id

        await delete_uc.execute(
            DeleteConversationInput(
                conversation_id=conv_a1.id,
                tenant_id=tenant_a.id,
                user_id=user_1.id,
            )
        )
        with pytest.raises(ResourceNotFoundException):
            await get_uc.execute(
                GetConversationInput(
                    conversation_id=conv_a1.id,
                    tenant_id=tenant_a.id,
                    user_id=user_1.id,
                )
            )

    async def test_list_pagination_orders_newest_first_and_recent_messages_window(
        self, session: AsyncSession
    ) -> None:
        tenant = await TenantFactory.create(session)
        user = await UserFactory.create(session)
        repo = ConversationSQLAlchemyRepository(session=session)
        create_uc = CreateConversationUseCase(conversation_repo=repo)
        list_uc = ListConversationsUseCase(conversation_repo=repo)

        first = await create_uc.execute(
            CreateConversationInput(tenant_id=tenant.id, user_id=user.id, title="Primeira")
        )
        second = await create_uc.execute(
            CreateConversationInput(tenant_id=tenant.id, user_id=user.id, title="Segunda")
        )

        # Ao adicionar mensagens na primeira conversa, ela passa a ser a mais recente
        for i in range(5):
            await repo.add_message(
                ChatMessage(
                    id=uuid4(),
                    conversation_id=first.id,
                    role="user" if i % 2 == 0 else "assistant",
                    content=f"Mensagem {i + 1}",
                )
            )

        listed = await list_uc.execute(
            ListConversationsInput(tenant_id=tenant.id, user_id=user.id, limit=10, offset=0)
        )
        assert [c.id for c in listed] == [first.id, second.id]

        paginated = await list_uc.execute(
            ListConversationsInput(tenant_id=tenant.id, user_id=user.id, limit=1, offset=1)
        )
        assert [c.id for c in paginated] == [second.id]

        # Janela deslizante: últimas 3 mensagens em ordem cronológica
        recent = await repo.get_recent_messages(conversation_id=first.id, limit=3)
        assert [m.content for m in recent] == ["Mensagem 3", "Mensagem 4", "Mensagem 5"]
