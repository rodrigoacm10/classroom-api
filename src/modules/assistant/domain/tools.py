from typing import Any

from modules.assistant.domain.entities.knowledge_chunk import RetrievedChunk

SEARCH_LOCUS_DOCS_TOOL_NAME = "search_locus_docs"

SEARCH_LOCUS_DOCS_DECLARATION: dict[str, Any] = {
    "name": SEARCH_LOCUS_DOCS_TOOL_NAME,
    "description": (
        "Busca na documentação oficial do Locus (guias de uso, rotas do painel web, "
        "regras de negócio de chamadas ao vivo, geofencing, auditoria de presença, "
        "turmas, salas, relatórios, membros e convites). "
        "Invoque esta ferramenta sempre que o usuário perguntar como realizar uma "
        "ação no sistema, onde fica uma funcionalidade ou quais são as regras do Locus."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "query": {
                "type": "STRING",
                "description": (
                    "Consulta em português descrevendo o tópico, funcionalidade ou "
                    "dúvida a buscar na documentação do Locus."
                ),
            }
        },
        "required": ["query"],
    },
}


def get_assistant_tools() -> list[dict[str, Any]]:
    """Retorna as declarações de ferramentas disponíveis para o assistente V1."""
    return [SEARCH_LOCUS_DOCS_DECLARATION]


def format_retrieved_chunks_for_tool(chunks: list[RetrievedChunk]) -> str:
    """Formata os trechos recuperados pelo Hybrid RAG para retorno à ferramenta do LLM."""
    if not chunks:
        return (
            "Nenhum trecho relevante foi encontrado na documentação para esta consulta "
            "e para o papel do usuário atual."
        )

    blocks: list[str] = []
    for idx, chunk in enumerate(chunks, start=1):
        routes_str = ", ".join(chunk.routes) if chunk.routes else "N/A"
        blocks.append(
            f"[Fonte {idx}] Documento: {chunk.doc_slug} | Seção: {chunk.section_title}\n"
            f"Rotas relacionadas: {routes_str}\n"
            f"Conteúdo:\n{chunk.content}"
        )
    return "\n\n---\n\n".join(blocks)
