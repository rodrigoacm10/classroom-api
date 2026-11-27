from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class DocumentChunk:
    """Chunk de documentação gerado pelo parser antes de receber embedding."""

    doc_slug: str
    section_title: str
    content: str
    routes: list[str]
    allowed_roles: list[str]
    content_hash: str


@dataclass
class KnowledgeChunk:
    """Chunk persistido na base vetorial com embedding gerado."""

    id: UUID
    doc_slug: str
    section_title: str
    content: str
    routes: list[str]
    allowed_roles: list[str]
    content_hash: str
    embedding: list[float]
    updated_at: datetime | None = None


@dataclass(frozen=True)
class RetrievedChunk:
    """Chunk retornado pela busca vetorial, textual ou híbrida (RRF)."""

    chunk_id: UUID
    doc_slug: str
    section_title: str
    content: str
    routes: list[str]
    score: float


@dataclass(frozen=True)
class SourceCitation:
    """Referência de documentação devolvida ao cliente junto da resposta."""

    doc_slug: str
    section_title: str
    routes: list[str]
