from pathlib import Path

import pytest

from modules.assistant.application.use_cases.knowledge.ingest_help_docs import (
    IngestHelpDocsInput,
    IngestHelpDocsUseCase,
)
from modules.assistant.domain.entities.knowledge_chunk import KnowledgeChunk, RetrievedChunk
from modules.assistant.infra.gemini.gemini_embedding_provider import GeminiEmbeddingProvider
from shared.enums.user_role import UserRole


class FakeEmbeddingProvider:
    def __init__(self, dims: int = 4) -> None:
        self.dims = dims
        self.embed_document_calls: list[list[str]] = []

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.embed_document_calls.append(list(texts))
        return [[float(i + 1)] * self.dims for i in range(len(texts))]

    async def embed_query(self, text: str) -> list[float]:
        return [0.5] * self.dims


class FakeKnowledgeRepository:
    def __init__(self) -> None:
        self.chunks: list[KnowledgeChunk] = []

    async def get_existing_hashes(self, doc_slug: str) -> set[str]:
        return {c.content_hash for c in self.chunks if c.doc_slug == doc_slug}

    async def upsert_chunks(self, chunks: list[KnowledgeChunk]) -> int:
        self.chunks.extend(chunks)
        return len(chunks)

    async def delete_chunks_not_in(self, doc_slug: str, valid_hashes: set[str]) -> int:
        before = len(self.chunks)
        self.chunks = [
            c for c in self.chunks if c.doc_slug != doc_slug or c.content_hash in valid_hashes
        ]
        return before - len(self.chunks)

    async def vector_search(
        self,
        *,
        query_embedding: list[float],
        user_role: UserRole,
        limit: int = 10,
    ) -> list[RetrievedChunk]:
        return []

    async def full_text_search(
        self,
        *,
        query_text: str,
        user_role: UserRole,
        limit: int = 10,
    ) -> list[RetrievedChunk]:
        return []


class TestIngestHelpDocsUseCase:
    async def test_first_run_embeds_and_second_run_skips_unchanged_chunks(
        self, tmp_path: Path
    ) -> None:
        doc_file = tmp_path / "01-guia.md"
        doc_file.write_text(
            "---\n"
            'topic: "Guia"\n'
            "routes:\n"
            '  - "/dashboard"\n'
            "allowed_roles:\n"
            '  - "ALL"\n'
            "---\n\n"
            "# Guia\n\n"
            "## Seção A\n\nConteúdo A.\n\n"
            "## Seção B\n\nConteúdo B.\n",
            encoding="utf-8",
        )

        repo = FakeKnowledgeRepository()
        embedder = FakeEmbeddingProvider()
        use_case = IngestHelpDocsUseCase(knowledge_repo=repo, embedding_provider=embedder)

        first = await use_case.execute(IngestHelpDocsInput(docs_dir=tmp_path))
        assert first.docs_processed == 1
        assert first.chunks_embedded == 2
        assert first.chunks_skipped == 0
        assert first.chunks_deleted == 0
        assert len(repo.chunks) == 2
        assert len(embedder.embed_document_calls) == 1

        second = await use_case.execute(IngestHelpDocsInput(docs_dir=tmp_path))
        assert second.docs_processed == 1
        assert second.chunks_embedded == 0
        assert second.chunks_skipped == 2
        assert second.chunks_deleted == 0
        # Segunda execução idempotente não faz nenhuma chamada de embedding
        assert len(embedder.embed_document_calls) == 1

    async def test_modified_section_reembeds_only_changed_chunk_and_deletes_stale(
        self, tmp_path: Path
    ) -> None:
        doc_file = tmp_path / "01-guia.md"
        doc_file.write_text(
            "# Guia\n\n## Seção A\n\nConteúdo A.\n\n## Seção B\n\nConteúdo B.\n",
            encoding="utf-8",
        )

        repo = FakeKnowledgeRepository()
        embedder = FakeEmbeddingProvider()
        use_case = IngestHelpDocsUseCase(knowledge_repo=repo, embedding_provider=embedder)

        await use_case.execute(IngestHelpDocsInput(docs_dir=tmp_path))

        # Altera apenas a Seção B
        doc_file.write_text(
            "# Guia\n\n## Seção A\n\nConteúdo A.\n\n## Seção B\n\nConteúdo B atualizado.\n",
            encoding="utf-8",
        )

        updated = await use_case.execute(IngestHelpDocsInput(docs_dir=tmp_path))
        assert updated.chunks_embedded == 1
        assert updated.chunks_skipped == 1
        assert updated.chunks_deleted == 1
        assert len(repo.chunks) == 2
        assert any("Conteúdo B atualizado." in c.content for c in repo.chunks)

    async def test_raises_when_docs_dir_does_not_exist(self, tmp_path: Path) -> None:
        use_case = IngestHelpDocsUseCase(
            knowledge_repo=FakeKnowledgeRepository(),
            embedding_provider=FakeEmbeddingProvider(),
        )
        with pytest.raises(FileNotFoundError):
            await use_case.execute(IngestHelpDocsInput(docs_dir=tmp_path / "missing"))


class TestGeminiEmbeddingProvider:
    def test_raises_when_api_key_is_empty(self) -> None:
        with pytest.raises(ValueError, match="GEMINI_API_KEY"):
            GeminiEmbeddingProvider(api_key="")
