from fastapi import HTTPException, status

from config.settings import settings
from modules.assistant.domain.services.embedding_provider import EmbeddingProvider
from modules.assistant.domain.services.llm_provider import LLMProvider
from modules.assistant.infra.gemini.gemini_embedding_provider import GeminiEmbeddingProvider
from modules.assistant.infra.gemini.gemini_llm_provider import GeminiLLMProvider


def get_llm_provider() -> LLMProvider:
    """Fornece o adapter de LLM (Gemini), lançando 503 se a GEMINI_API_KEY não estiver configurada."""
    if not settings.gemini_api_key or not settings.gemini_api_key.strip():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "O Assistente Locus está temporariamente indisponível "
                "(GEMINI_API_KEY não configurada no servidor)."
            ),
        )
    return GeminiLLMProvider(
        api_key=settings.gemini_api_key,
        model=settings.gemini_chat_model,
    )


def get_embedding_provider() -> EmbeddingProvider:
    """Fornece o adapter de embeddings (Gemini), lançando 503 se a GEMINI_API_KEY estiver ausente."""
    if not settings.gemini_api_key or not settings.gemini_api_key.strip():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "O Assistente Locus está temporariamente indisponível "
                "(GEMINI_API_KEY não configurada no servidor)."
            ),
        )
    return GeminiEmbeddingProvider(
        api_key=settings.gemini_api_key,
        model=settings.gemini_embedding_model,
    )
