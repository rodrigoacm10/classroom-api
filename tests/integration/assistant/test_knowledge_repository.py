from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from modules.assistant.domain.entities.knowledge_chunk import KnowledgeChunk
from modules.assistant.infra.repositories.knowledge_sqlalchemy_repository import (
    KnowledgeSQLAlchemyRepository,
)
from shared.enums.user_role import UserRole


def _unit_vector(hot_index: int, dims: int = 768) -> list[float]:
    vec = [0.0] * dims
    vec[hot_index] = 1.0
    return vec


class TestKnowledgeSQLAlchemyRepository:
    async def test_vector_search_ranks_closest_chunk_and_filters_by_role(
        self, session: AsyncSession
    ) -> None:
        repo = KnowledgeSQLAlchemyRepository(session=session)

        chunks = [
            KnowledgeChunk(
                id=uuid4(),
                doc_slug="04-chamadas-ao-vivo",
                section_title="Chamadas ao Vivo > Como abrir uma chamada",
                content="Para abrir uma chamada acesse /dashboard/chamadas/nova.",
                routes=["/dashboard/chamadas/nova"],
                allowed_roles=["admin", "professor"],
                content_hash="hash-chamada",
                embedding=_unit_vector(0),
            ),
            KnowledgeChunk(
                id=uuid4(),
                doc_slug="07-membros-convites-e-instituicao",
                section_title="Convites > Como convidar membros",
                content="Acesse /dashboard/convites para enviar convites.",
                routes=["/dashboard/convites"],
                allowed_roles=["admin", "coordenador"],
                content_hash="hash-convites",
                embedding=_unit_vector(0),  # Mesmo vetor, mas restrito a admin/coordenador
            ),
            KnowledgeChunk(
                id=uuid4(),
                doc_slug="01-visao-geral-e-papeis",
                section_title="Visão Geral > O que é o Locus",
                content="Plataforma de presença acadêmica com geofencing.",
                routes=["/dashboard"],
                allowed_roles=["ALL"],
                content_hash="hash-geral",
                embedding=_unit_vector(1),
            ),
        ]
        await repo.upsert_chunks(chunks)

        prof_results = await repo.vector_search(
            query_embedding=_unit_vector(0),
            user_role=UserRole.PROFESSOR,
            limit=5,
        )
        prof_slugs = [r.doc_slug for r in prof_results]
        assert "04-chamadas-ao-vivo" in prof_slugs
        assert "01-visao-geral-e-papeis" in prof_slugs
        assert "07-membros-convites-e-instituicao" not in prof_slugs
        assert prof_results[0].doc_slug == "04-chamadas-ao-vivo"

        admin_results = await repo.vector_search(
            query_embedding=_unit_vector(0),
            user_role=UserRole.ADMIN,
            limit=5,
        )
        admin_slugs = [r.doc_slug for r in admin_results]
        assert "07-membros-convites-e-instituicao" in admin_slugs

    async def test_full_text_search_matches_portuguese_terms_and_respects_role(
        self, session: AsyncSession
    ) -> None:
        repo = KnowledgeSQLAlchemyRepository(session=session)

        await repo.upsert_chunks(
            [
                KnowledgeChunk(
                    id=uuid4(),
                    doc_slug="04-chamadas-ao-vivo",
                    section_title="Chamadas ao Vivo > Como abrir uma chamada",
                    content="Gera um código de 6 caracteres e notifica os alunos matriculados.",
                    routes=["/dashboard/chamadas/nova"],
                    allowed_roles=["admin", "professor"],
                    content_hash="hash-fts-1",
                    embedding=_unit_vector(2),
                ),
                KnowledgeChunk(
                    id=uuid4(),
                    doc_slug="07-membros-convites-e-instituicao",
                    section_title="Convites > Enviar convite",
                    content="Convite de novo membro com link válido por 72 horas.",
                    routes=["/dashboard/convites"],
                    allowed_roles=["admin"],
                    content_hash="hash-fts-2",
                    embedding=_unit_vector(3),
                ),
            ]
        )

        # Stemming em português: "chamadas" casa com "chamada"
        fts_prof = await repo.full_text_search(
            query_text="abrir chamadas caracteres",
            user_role=UserRole.PROFESSOR,
            limit=5,
        )
        assert len(fts_prof) == 1
        assert fts_prof[0].doc_slug == "04-chamadas-ao-vivo"

        # Professor não enxerga chunk restrito a admin mesmo buscando palavra exata
        fts_restricted = await repo.full_text_search(
            query_text="convite 72 horas",
            user_role=UserRole.PROFESSOR,
            limit=5,
        )
        assert fts_restricted == []
