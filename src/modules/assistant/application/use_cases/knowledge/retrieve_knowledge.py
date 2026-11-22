from dataclasses import dataclass
from uuid import UUID

from modules.assistant.domain.entities.knowledge_chunk import RetrievedChunk
from modules.assistant.domain.repositories.knowledge_repository import KnowledgeRepository
from modules.assistant.domain.services.embedding_provider import EmbeddingProvider
from shared.enums.user_role import UserRole


def reciprocal_rank_fusion(
    ranked_lists: list[list[RetrievedChunk]],
    *,
    k: int = 60,
    limit: int = 5,
) -> list[RetrievedChunk]:
    """Combina múltiplos rankings (ex.: vetorial + FTS) via Reciprocal Rank Fusion (RRF)."""
    scores: dict[UUID, float] = {}
    chunks_by_id: dict[UUID, RetrievedChunk] = {}

    for ranked in ranked_lists:
        for rank, chunk in enumerate(ranked, start=1):
            chunks_by_id.setdefault(chunk.chunk_id, chunk)
            scores[chunk.chunk_id] = scores.get(chunk.chunk_id, 0.0) + (1.0 / (k + rank))

    sorted_ids = sorted(scores, key=lambda cid: scores[cid], reverse=True)[:limit]
    return [
        RetrievedChunk(
            chunk_id=chunks_by_id[cid].chunk_id,
            doc_slug=chunks_by_id[cid].doc_slug,
            section_title=chunks_by_id[cid].section_title,
            content=chunks_by_id[cid].content,
            routes=list(chunks_by_id[cid].routes),
            score=scores[cid],
        )
        for cid in sorted_ids
    ]


@dataclass(frozen=True)
class RetrieveKnowledgeInput:
    query: str
    user_role: UserRole
    top_k: int = 5
    candidate_limit: int = 10


class RetrieveKnowledgeUseCase:
    """Executa busca híbrida (pgvector + tsvector + RRF) filtrada pelo papel do usuário."""

    def __init__(
        self,
        *,
        knowledge_repo: KnowledgeRepository,
        embedding_provider: EmbeddingProvider,
        rrf_k: int = 60,
    ) -> None:
        self._knowledge_repo = knowledge_repo
        self._embedding_provider = embedding_provider
        self._rrf_k = rrf_k

    async def execute(self, data: RetrieveKnowledgeInput) -> list[RetrievedChunk]:
        cleaned_query = data.query.strip()
        if not cleaned_query:
            return []

        query_embedding = await self._embedding_provider.embed_query(cleaned_query)

        vector_results = await self._knowledge_repo.vector_search(
            query_embedding=query_embedding,
            user_role=data.user_role,
            limit=data.candidate_limit,
        )
        fts_results = await self._knowledge_repo.full_text_search(
            query_text=cleaned_query,
            user_role=data.user_role,
            limit=data.candidate_limit,
        )

        return reciprocal_rank_fusion(
            [vector_results, fts_results],
            k=self._rrf_k,
            limit=data.top_k,
        )
