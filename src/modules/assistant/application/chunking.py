import hashlib
import json
import re
from dataclasses import dataclass

from modules.assistant.domain.entities.knowledge_chunk import DocumentChunk

_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.DOTALL)
_HEADING_RE = re.compile(r"^(#{1,3})\s+(.+?)\s*$")


@dataclass(frozen=True)
class DocumentMetadata:
    topic: str
    routes: list[str]
    allowed_roles: list[str]


def _unquote(value: str) -> str:
    stripped = value.strip()
    if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in ('"', "'"):
        return stripped[1:-1]
    return stripped


def parse_frontmatter(markdown: str) -> tuple[DocumentMetadata, str]:
    """Extrai frontmatter YAML simples (topic, routes, allowed_roles) e retorna o corpo."""
    match = _FRONTMATTER_RE.match(markdown)
    if not match:
        return DocumentMetadata(topic="", routes=[], allowed_roles=["ALL"]), markdown

    raw_header = match.group(1)
    body = markdown[match.end() :]

    topic = ""
    routes: list[str] = []
    allowed_roles: list[str] = []
    current_list_key: str | None = None

    for line in raw_header.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        if stripped.startswith("- ") and current_list_key is not None:
            item = _unquote(stripped[2:])
            if item:
                if current_list_key == "routes":
                    routes.append(item)
                elif current_list_key == "allowed_roles":
                    allowed_roles.append(item)
            continue

        if ":" in stripped:
            key, raw_value = stripped.split(":", 1)
            key = key.strip()
            value = _unquote(raw_value)
            if key == "topic":
                topic = value
                current_list_key = None
            elif key in ("routes", "allowed_roles"):
                current_list_key = key
                if value.startswith("[") and value.endswith("]"):
                    items = [_unquote(part) for part in value[1:-1].split(",") if part.strip()]
                    if key == "routes":
                        routes.extend(items)
                    else:
                        allowed_roles.extend(items)
                    current_list_key = None
            else:
                current_list_key = None

    if not allowed_roles:
        allowed_roles = ["ALL"]

    return DocumentMetadata(topic=topic, routes=routes, allowed_roles=allowed_roles), body


def compute_chunk_hash(
    *,
    doc_slug: str,
    section_title: str,
    content: str,
    routes: list[str],
    allowed_roles: list[str],
) -> str:
    """Calcula hash SHA-256 determinístico para pular re-embedding de chunks inalterados."""
    payload = json.dumps(
        {
            "doc_slug": doc_slug,
            "section_title": section_title,
            "content": content,
            "routes": routes,
            "allowed_roles": allowed_roles,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _split_long_text(text: str, *, max_chars: int, overlap_chars: int) -> list[str]:
    """Divide textos longos respeitando parágrafos/palavras com overlap configurável."""
    if len(text) <= max_chars:
        return [text]

    if overlap_chars >= max_chars:
        raise ValueError("overlap_chars deve ser menor que max_chars")

    chunks: list[str] = []
    start = 0
    length = len(text)

    while start < length:
        end = min(start + max_chars, length)
        if end < length:
            # Prefere quebrar em fim de parágrafo, depois quebra de linha, depois espaço
            split_at = text.rfind("\n\n", start, end)
            if split_at <= start:
                split_at = text.rfind("\n", start, end)
            if split_at <= start:
                split_at = text.rfind(" ", start, end)
            if split_at > start:
                end = split_at

        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)

        if end >= length:
            break

        next_start = max(end - overlap_chars, start + 1)
        # Evita começar no meio de uma palavra quando recuamos pelo overlap
        if next_start > start and next_start < length and not text[next_start - 1].isspace():
            space_idx = text.find(" ", next_start, end)
            if space_idx != -1:
                next_start = space_idx + 1
        start = next_start

    return chunks


def chunk_markdown_document(
    *,
    doc_slug: str,
    markdown: str,
    max_chars: int = 1200,
    overlap_chars: int = 150,
) -> list[DocumentChunk]:
    """Divide um documento Markdown em chunks conscientes de hierarquia de títulos."""
    metadata, body = parse_frontmatter(markdown)

    h1 = ""
    h2 = ""
    h3 = ""
    buffer: list[str] = []
    sections: list[tuple[str, str]] = []

    def current_title() -> str:
        parts = [part for part in (h1, h2, h3) if part]
        if parts:
            return " > ".join(parts)
        return metadata.topic or doc_slug

    def flush() -> None:
        content = "\n".join(buffer).strip()
        buffer.clear()
        if content:
            sections.append((current_title(), content))

    for line in body.splitlines():
        heading_match = _HEADING_RE.match(line)
        if heading_match:
            flush()
            level = len(heading_match.group(1))
            title = heading_match.group(2).strip()
            if level == 1:
                h1 = title
                h2 = ""
                h3 = ""
            elif level == 2:
                h2 = title
                h3 = ""
            else:
                h3 = title
        else:
            buffer.append(line)

    flush()

    result: list[DocumentChunk] = []
    for section_title, section_body in sections:
        pieces = _split_long_text(section_body, max_chars=max_chars, overlap_chars=overlap_chars)
        total_pieces = len(pieces)
        for index, piece in enumerate(pieces, start=1):
            final_title = (
                f"{section_title} (parte {index}/{total_pieces})"
                if total_pieces > 1
                else section_title
            )
            content_hash = compute_chunk_hash(
                doc_slug=doc_slug,
                section_title=final_title,
                content=piece,
                routes=metadata.routes,
                allowed_roles=metadata.allowed_roles,
            )
            result.append(
                DocumentChunk(
                    doc_slug=doc_slug,
                    section_title=final_title,
                    content=piece,
                    routes=list(metadata.routes),
                    allowed_roles=list(metadata.allowed_roles),
                    content_hash=content_hash,
                )
            )

    return result
