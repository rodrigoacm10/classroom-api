from google import genai
from google.genai import types

DEFAULT_EMBEDDING_DIMENSIONS = 768


class GeminiEmbeddingProvider:
    """Adapter de embeddings usando o SDK oficial google-genai."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "gemini-embedding-001",
        dimensions: int = DEFAULT_EMBEDDING_DIMENSIONS,
    ) -> None:
        if not api_key or not api_key.strip():
            raise ValueError(
                "GEMINI_API_KEY não configurada. Defina a variável no .env para gerar embeddings."
            )
        self._client = genai.Client(api_key=api_key.strip())
        self._model = model
        self._dimensions = dimensions

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        response = await self._client.aio.models.embed_content(
            model=self._model,
            contents=texts,
            config=types.EmbedContentConfig(
                task_type="RETRIEVAL_DOCUMENT",
                output_dimensionality=self._dimensions,
            ),
        )
        return self._extract_vectors(response, expected_count=len(texts))

    async def embed_query(self, text: str) -> list[float]:
        response = await self._client.aio.models.embed_content(
            model=self._model,
            contents=text,
            config=types.EmbedContentConfig(
                task_type="RETRIEVAL_QUERY",
                output_dimensionality=self._dimensions,
            ),
        )
        vectors = self._extract_vectors(response, expected_count=1)
        return vectors[0]

    @staticmethod
    def _extract_vectors(
        response: types.EmbedContentResponse,
        *,
        expected_count: int,
    ) -> list[list[float]]:
        embeddings = response.embeddings or []
        vectors: list[list[float]] = []
        for item in embeddings:
            if item.values is None:
                raise RuntimeError("Resposta de embedding do Gemini veio sem valores vetoriais.")
            vectors.append(list(item.values))

        if len(vectors) != expected_count:
            raise RuntimeError(
                f"Esperava {expected_count} embeddings do Gemini, mas recebeu {len(vectors)}."
            )
        return vectors
