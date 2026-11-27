from pathlib import Path

import pytest

from modules.assistant.application.chunking import (
    chunk_markdown_document,
    compute_chunk_hash,
    parse_frontmatter,
)


class TestParseFrontmatter:
    def test_parses_topic_routes_and_roles(self) -> None:
        md = (
            "---\n"
            'topic: "Chamadas ao vivo"\n'
            "routes:\n"
            '  - "/dashboard/chamadas"\n'
            '  - "/dashboard/chamadas/nova"\n'
            "allowed_roles:\n"
            '  - "admin"\n'
            '  - "professor"\n'
            "---\n\n"
            "# Chamadas\n"
            "Conteúdo.\n"
        )
        meta, body = parse_frontmatter(md)

        assert meta.topic == "Chamadas ao vivo"
        assert meta.routes == ["/dashboard/chamadas", "/dashboard/chamadas/nova"]
        assert meta.allowed_roles == ["admin", "professor"]
        assert body.strip().startswith("# Chamadas")

    def test_defaults_when_frontmatter_is_absent(self) -> None:
        md = "# Sem Frontmatter\n\nTexto simples."
        meta, body = parse_frontmatter(md)

        assert meta.topic == ""
        assert meta.routes == []
        assert meta.allowed_roles == ["ALL"]
        assert body == md


class TestChunkMarkdownDocument:
    def test_preserves_heading_hierarchy_and_skips_empty_sections(self) -> None:
        md = (
            "---\n"
            'topic: "Salas"\n'
            "routes:\n"
            '  - "/dashboard/salas"\n'
            "allowed_roles:\n"
            '  - "professor"\n'
            "---\n\n"
            "# Salas Físicas\n\n"
            "## Como cadastrar\n\n"
            "Passo 1: acesse o menu Salas.\n\n"
            "### Dica de raio\n\n"
            "Use 50 metros como padrão.\n\n"
            "## Seção vazia\n\n"
            "## Editar sala\n\n"
            "Clique em Editar.\n"
        )

        chunks = chunk_markdown_document(doc_slug="02-salas", markdown=md)

        assert len(chunks) == 3
        assert chunks[0].section_title == "Salas Físicas > Como cadastrar"
        assert chunks[1].section_title == "Salas Físicas > Como cadastrar > Dica de raio"
        assert chunks[2].section_title == "Salas Físicas > Editar sala"
        assert all(c.routes == ["/dashboard/salas"] for c in chunks)
        assert all(c.allowed_roles == ["professor"] for c in chunks)

    def test_splits_long_section_with_overlap(self) -> None:
        paragraph = "Esta é uma frase de teste para validar a divisão de chunks longos. " * 10
        md = f"# Guia\n\n## Seção longa\n\n{paragraph.strip()}\n"

        chunks = chunk_markdown_document(
            doc_slug="long-doc",
            markdown=md,
            max_chars=200,
            overlap_chars=40,
        )

        assert len(chunks) > 1
        assert chunks[0].section_title.startswith("Guia > Seção longa (parte 1/")
        assert all(len(c.content) <= 200 for c in chunks)
        # Verifica sobreposição real entre chunks consecutivos
        tail_words = chunks[0].content.split()[-3:]
        assert any(word in chunks[1].content for word in tail_words)

    def test_raises_when_overlap_is_invalid(self) -> None:
        md = "# Guia\n\n## Seção\n\n" + ("a " * 200)
        with pytest.raises(ValueError, match="overlap_chars"):
            chunk_markdown_document(doc_slug="bad", markdown=md, max_chars=100, overlap_chars=100)

    def test_content_hash_is_deterministic_and_sensitive_to_metadata(self) -> None:
        h1 = compute_chunk_hash(
            doc_slug="doc",
            section_title="Sec",
            content="Texto",
            routes=["/a"],
            allowed_roles=["professor"],
        )
        h2 = compute_chunk_hash(
            doc_slug="doc",
            section_title="Sec",
            content="Texto",
            routes=["/a"],
            allowed_roles=["professor"],
        )
        h3 = compute_chunk_hash(
            doc_slug="doc",
            section_title="Sec",
            content="Texto",
            routes=["/a"],
            allowed_roles=["admin"],
        )

        assert h1 == h2
        assert h1 != h3

    def test_chunks_all_curated_locus_help_docs(self) -> None:
        help_dir = Path(__file__).resolve().parents[3] / "docs" / "help"
        files = sorted(help_dir.glob("*.md"))

        assert len(files) == 7

        total_chunks = 0
        for path in files:
            chunks = chunk_markdown_document(
                doc_slug=path.stem,
                markdown=path.read_text(encoding="utf-8"),
            )
            assert len(chunks) >= 2, f"{path.name} deveria gerar ao menos 2 chunks"
            for chunk in chunks:
                assert chunk.content.strip()
                assert chunk.section_title.strip()
                assert chunk.allowed_roles
                assert len(chunk.content_hash) == 64
            total_chunks += len(chunks)

        assert total_chunks >= 20
