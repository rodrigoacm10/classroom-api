"""
CLI idempotente para ingerir os guias de ajuda (docs/help/*.md) no PostgreSQL (pgvector).

Uso:
    uv run python scripts/ingest_help_docs.py
"""

import asyncio
import sys
from pathlib import Path

src_dir = str(Path(__file__).resolve().parent.parent / "src")
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

from config.settings import settings
from infra.database.session import AsyncSessionLocal
from modules.assistant.application.use_cases.knowledge.ingest_help_docs import (
    IngestHelpDocsInput,
    IngestHelpDocsUseCase,
)
from modules.assistant.infra.gemini.gemini_embedding_provider import GeminiEmbeddingProvider
from modules.assistant.infra.repositories.knowledge_sqlalchemy_repository import (
    KnowledgeSQLAlchemyRepository,
)


async def main() -> int:
    if not settings.gemini_api_key.strip():
        print(
            "Erro: GEMINI_API_KEY não configurada no .env.\n"
            "Obtenha uma chave em https://aistudio.google.com/apikey e defina GEMINI_API_KEY no classroom-api/.env.",
            file=sys.stderr,
        )
        return 1

    docs_dir = Path(__file__).resolve().parent.parent / "docs" / "help"
    embedding_provider = GeminiEmbeddingProvider(
        api_key=settings.gemini_api_key,
        model=settings.gemini_embedding_model,
    )

    async with AsyncSessionLocal() as session:
        repo = KnowledgeSQLAlchemyRepository(session=session)
        use_case = IngestHelpDocsUseCase(
            knowledge_repo=repo,
            embedding_provider=embedding_provider,
        )
        result = await use_case.execute(IngestHelpDocsInput(docs_dir=docs_dir))
        await session.commit()

    print(
        f"Ingestão concluída: {result.docs_processed} documentos | "
        f"{result.chunks_embedded} chunks embedados | "
        f"{result.chunks_skipped} inalterados (pulados) | "
        f"{result.chunks_deleted} obsoletos removidos."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
