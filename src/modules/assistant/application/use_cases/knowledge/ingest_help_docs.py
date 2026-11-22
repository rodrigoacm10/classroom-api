from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from modules.assistant.application.chunking import chunk_markdown_document
from modules.assistant.domain.entities.knowledge_chunk import DocumentChunk, KnowledgeChunk
from modules.assistant.domain.repositories.knowledge_repository import KnowledgeRepository
from modules.assistant.domain.services.embedding_provider import EmbeddingProvider


@dataclass(frozen=True)
class IngestHelpDocsInput:
    docs_dir: Path
    max_chars: int = 1200
    overlap_chars: int = 150
    batch_size: int = 32


@dataclass(frozen=True)
class IngestHelpDocsResult:
    docs_processed: int
    chunks_embedded: int
    chunks_skipped: int
    chunks_deleted: int


class IngestHelpDocsUseCase:
    """Ingere guias Markdown em knowledge_chunks de forma idempotente via content_hash."""

    def __init__(
        self,
        *,
        knowledge_repo: KnowledgeRepository,
        embedding_provider: EmbeddingProvider,
    ) -> None:
        self._knowledge_repo = knowledge_repo
        self._embedding_provider = embedding_provider

    async def execute(self, data: IngestHelpDocsInput) -> IngestHelpDocsResult:
        if not data.docs_dir.exists():
            raise FileNotFoundError(f"Diretório de documentação não encontrado: {data.docs_dir}")

        files = sorted(data.docs_dir.glob("*.md"))
        docs_processed = 0
        chunks_embedded = 0
        chunks_skipped = 0
        chunks_deleted = 0

        for path in files:
            doc_slug = path.stem
            markdown = path.read_text(encoding="utf-8")
            doc_chunks = chunk_markdown_document(
                doc_slug=doc_slug,
                markdown=markdown,
                max_chars=data.max_chars,
                overlap_chars=data.overlap_chars,
            )

            existing_hashes = await self._knowledge_repo.get_existing_hashes(doc_slug)
            valid_hashes = {chunk.content_hash for chunk in doc_chunks}

            new_chunks = [c for c in doc_chunks if c.content_hash not in existing_hashes]
            chunks_skipped += len(doc_chunks) - len(new_chunks)

            if new_chunks:
                knowledge_chunks = await self._embed_in_batches(
                    new_chunks, batch_size=data.batch_size
                )
                await self._knowledge_repo.upsert_chunks(knowledge_chunks)
                chunks_embedded += len(knowledge_chunks)

            deleted = await self._knowledge_repo.delete_chunks_not_in(doc_slug, valid_hashes)
            chunks_deleted += deleted
            docs_processed += 1

        return IngestHelpDocsResult(
            docs_processed=docs_processed,
            chunks_embedded=chunks_embedded,
            chunks_skipped=chunks_skipped,
            chunks_deleted=chunks_deleted,
        )

    async def _embed_in_batches(
        self,
        chunks: list[DocumentChunk],
        *,
        batch_size: int,
    ) -> list[KnowledgeChunk]:
        results: list[KnowledgeChunk] = []
        for start in range(0, len(chunks), batch_size):
            batch = chunks[start : start + batch_size]
            texts = [f"{c.section_title}\n\n{c.content}" for c in batch]
            vectors = await self._embedding_provider.embed_documents(texts)
            for doc_chunk, vector in zip(batch, vectors, strict=True):
                results.append(
                    KnowledgeChunk(
                        id=uuid4(),
                        doc_slug=doc_chunk.doc_slug,
                        section_title=doc_chunk.section_title,
                        content=doc_chunk.content,
                        routes=list(doc_chunk.routes),
                        allowed_roles=list(doc_chunk.allowed_roles),
                        content_hash=doc_chunk.content_hash,
                        embedding=vector,
                    )
                )
        return results
