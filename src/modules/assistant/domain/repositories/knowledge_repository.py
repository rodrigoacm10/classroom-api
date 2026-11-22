from typing import Protocol

from modules.assistant.domain.entities.knowledge_chunk import KnowledgeChunk, RetrievedChunk
from shared.enums.user_role import UserRole


class KnowledgeRepository(Protocol):
    """Contrato de persistência e busca (vetorial + FTS) da base de conhecimento."""

    async def get_existing_hashes(self, doc_slug: str) -> set[str]: ...

    async def upsert_chunks(self, chunks: list[KnowledgeChunk]) -> int: ...

    async def delete_chunks_not_in(self, doc_slug: str, valid_hashes: set[str]) -> int: ...

    async def vector_search(
        self,
        *,
        query_embedding: list[float],
        user_role: UserRole,
        limit: int = 10,
    ) -> list[RetrievedChunk]: ...

    async def full_text_search(
        self,
        *,
        query_text: str,
        user_role: UserRole,
        limit: int = 10,
    ) -> list[RetrievedChunk]: ...
