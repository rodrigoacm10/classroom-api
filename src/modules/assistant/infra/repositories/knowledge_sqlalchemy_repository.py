from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from infra.database.models.knowledge_chunk import KnowledgeChunkModel
from modules.assistant.domain.entities.knowledge_chunk import KnowledgeChunk, RetrievedChunk
from shared.enums.user_role import UserRole


class KnowledgeSQLAlchemyRepository:
    """Repositório PostgreSQL (pgvector + tsvector) para knowledge_chunks."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_existing_hashes(self, doc_slug: str) -> set[str]:
        stmt = select(KnowledgeChunkModel.content_hash).where(
            KnowledgeChunkModel.doc_slug == doc_slug
        )
        result = await self._session.execute(stmt)
        return set(result.scalars().all())

    async def upsert_chunks(self, chunks: list[KnowledgeChunk]) -> int:
        if not chunks:
            return 0

        models = [
            KnowledgeChunkModel(
                id=chunk.id,
                doc_slug=chunk.doc_slug,
                section_title=chunk.section_title,
                content=chunk.content,
                routes=chunk.routes,
                allowed_roles=chunk.allowed_roles,
                content_hash=chunk.content_hash,
                embedding=chunk.embedding,
            )
            for chunk in chunks
        ]
        self._session.add_all(models)
        await self._session.flush()
        return len(models)

    async def delete_chunks_not_in(self, doc_slug: str, valid_hashes: set[str]) -> int:
        stmt = delete(KnowledgeChunkModel).where(KnowledgeChunkModel.doc_slug == doc_slug)
        if valid_hashes:
            stmt = stmt.where(KnowledgeChunkModel.content_hash.notin_(valid_hashes))

        result = await self._session.execute(stmt)
        await self._session.flush()
        return int(getattr(result, "rowcount", 0) or 0)

    @staticmethod
    def _role_filter(user_role: UserRole):
        return or_(
            KnowledgeChunkModel.allowed_roles.contains(["ALL"]),
            KnowledgeChunkModel.allowed_roles.contains([user_role.value]),
        )

    async def vector_search(
        self,
        *,
        query_embedding: list[float],
        user_role: UserRole,
        limit: int = 10,
    ) -> list[RetrievedChunk]:
        distance = KnowledgeChunkModel.embedding.cosine_distance(query_embedding)
        similarity = (1.0 - distance).label("score")

        stmt = (
            select(KnowledgeChunkModel, similarity)
            .where(self._role_filter(user_role))
            .order_by(distance.asc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return [
            RetrievedChunk(
                chunk_id=model.id,
                doc_slug=model.doc_slug,
                section_title=model.section_title,
                content=model.content,
                routes=list(model.routes),
                score=float(score),
            )
            for model, score in result.all()
        ]

    async def full_text_search(
        self,
        *,
        query_text: str,
        user_role: UserRole,
        limit: int = 10,
    ) -> list[RetrievedChunk]:
        cleaned = query_text.strip()
        if not cleaned:
            return []

        ts_query = func.plainto_tsquery("portuguese", cleaned)
        rank = func.ts_rank(KnowledgeChunkModel.search_vector, ts_query).label("score")

        stmt = (
            select(KnowledgeChunkModel, rank)
            .where(
                self._role_filter(user_role),
                KnowledgeChunkModel.search_vector.op("@@")(ts_query),
            )
            .order_by(rank.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return [
            RetrievedChunk(
                chunk_id=model.id,
                doc_slug=model.doc_slug,
                section_title=model.section_title,
                content=model.content,
                routes=list(model.routes),
                score=float(score),
            )
            for model, score in result.all()
        ]
