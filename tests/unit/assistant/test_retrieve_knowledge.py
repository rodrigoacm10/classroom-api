from uuid import UUID, uuid4

from modules.assistant.application.use_cases.knowledge.retrieve_knowledge import (
    RetrieveKnowledgeInput,
    RetrieveKnowledgeUseCase,
    reciprocal_rank_fusion,
)
from modules.assistant.domain.entities.knowledge_chunk import KnowledgeChunk, RetrievedChunk
from shared.enums.user_role import UserRole


def _make_chunk(
    doc_slug: str, section: str, score: float = 0.5, cid: UUID | None = None
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=cid or uuid4(),
        doc_slug=doc_slug,
        section_title=section,
        content=f"Conteúdo de {section}",
        routes=["/dashboard"],
        score=score,
    )


class FakeEmbeddingProvider:
    def __init__(self) -> None:
        self.queries: list[str] = []

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[0.1] * 4 for _ in texts]

    async def embed_query(self, text: str) -> list[float]:
        self.queries.append(text)
        return [0.25] * 4


class FakeHybridKnowledgeRepository:
    def __init__(
        self,
        *,
        vector_results: list[RetrievedChunk],
        fts_results: list[RetrievedChunk],
    ) -> None:
        self._vector_results = vector_results
        self._fts_results = fts_results
        self.last_role: UserRole | None = None
        self.last_limit: int | None = None

    async def get_existing_hashes(self, doc_slug: str) -> set[str]:
        return set()

    async def upsert_chunks(self, chunks: list[KnowledgeChunk]) -> int:
        return len(chunks)

    async def delete_chunks_not_in(self, doc_slug: str, valid_hashes: set[str]) -> int:
        return 0

    async def vector_search(
        self,
        *,
        query_embedding: list[float],
        user_role: UserRole,
        limit: int = 10,
    ) -> list[RetrievedChunk]:
        self.last_role = user_role
        self.last_limit = limit
        return list(self._vector_results[:limit])

    async def full_text_search(
        self,
        *,
        query_text: str,
        user_role: UserRole,
        limit: int = 10,
    ) -> list[RetrievedChunk]:
        self.last_role = user_role
        self.last_limit = limit
        return list(self._fts_results[:limit])


class TestReciprocalRankFusion:
    def test_boosts_chunk_present_in_both_vector_and_fts_lists(self) -> None:
        shared_id = uuid4()
        vec_only = _make_chunk("01-visao", "Visão Geral", score=0.95)
        shared = _make_chunk("04-chamadas", "Abrir Chamada", score=0.80, cid=shared_id)
        fts_only = _make_chunk("05-auditoria", "Auditoria", score=0.90)

        fused = reciprocal_rank_fusion(
            [
                [vec_only, shared],  # shared is rank 2 in vector
                [fts_only, shared],  # shared is rank 2 in FTS
            ],
            k=60,
            limit=3,
        )

        # shared: 1/62 + 1/62 = 2/62 > 1/61 (vec_only e fts_only)
        assert fused[0].chunk_id == shared_id
        assert len(fused) == 3

    def test_handles_disjoint_and_empty_lists_with_limit(self) -> None:
        c1 = _make_chunk("01", "A")
        c2 = _make_chunk("02", "B")
        c3 = _make_chunk("03", "C")

        fused = reciprocal_rank_fusion([[c1, c2], [], [c3]], k=60, limit=2)
        assert len(fused) == 2


class TestRetrieveKnowledgeUseCase:
    async def test_empty_query_returns_empty_without_calling_embedder(self) -> None:
        embedder = FakeEmbeddingProvider()
        repo = FakeHybridKnowledgeRepository(vector_results=[], fts_results=[])
        use_case = RetrieveKnowledgeUseCase(knowledge_repo=repo, embedding_provider=embedder)

        result = await use_case.execute(
            RetrieveKnowledgeInput(query="   ", user_role=UserRole.PROFESSOR)
        )

        assert result == []
        assert embedder.queries == []

    async def test_fuses_vector_and_fts_and_forwards_user_role(self) -> None:
        shared_id = uuid4()
        c_vec = _make_chunk("02-salas", "Salas")
        c_shared = _make_chunk("04-chamadas", "Como abrir uma chamada", cid=shared_id)
        c_fts = _make_chunk("06-relatorios", "Relatórios")

        embedder = FakeEmbeddingProvider()
        repo = FakeHybridKnowledgeRepository(
            vector_results=[c_vec, c_shared],
            fts_results=[c_fts, c_shared],
        )
        use_case = RetrieveKnowledgeUseCase(knowledge_repo=repo, embedding_provider=embedder)

        results = await use_case.execute(
            RetrieveKnowledgeInput(
                query="como abrir uma chamada",
                user_role=UserRole.PROFESSOR,
                top_k=2,
                candidate_limit=8,
            )
        )

        assert embedder.queries == ["como abrir uma chamada"]
        assert repo.last_role == UserRole.PROFESSOR
        assert repo.last_limit == 8
        assert len(results) == 2
        assert results[0].chunk_id == shared_id
