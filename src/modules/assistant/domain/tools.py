from typing import Any

from modules.assistant.domain.entities.knowledge_chunk import RetrievedChunk
from shared.enums.user_role import UserRole

SEARCH_LOCUS_DOCS_TOOL_NAME = "search_locus_docs"
GET_DASHBOARD_OVERVIEW_TOOL_NAME = "get_dashboard_overview"
LIST_CLASSES_TOOL_NAME = "list_classes"
GET_CLASS_ATTENDANCE_REPORT_TOOL_NAME = "get_class_attendance_report"
LIST_ATTENDANCE_SESSIONS_TOOL_NAME = "list_attendance_sessions"
GET_SESSION_AUDIT_SUMMARY_TOOL_NAME = "get_session_audit_summary"
GET_STUDENT_ATTENDANCE_TOOL_NAME = "get_student_attendance"
LIST_ROOMS_TOOL_NAME = "list_rooms"
GET_INSTITUTION_MEMBERS_SUMMARY_TOOL_NAME = "get_institution_members_summary"

LIVE_DATA_TOOL_NAMES: frozenset[str] = frozenset(
    {
        GET_DASHBOARD_OVERVIEW_TOOL_NAME,
        LIST_CLASSES_TOOL_NAME,
        GET_CLASS_ATTENDANCE_REPORT_TOOL_NAME,
        LIST_ATTENDANCE_SESSIONS_TOOL_NAME,
        GET_SESSION_AUDIT_SUMMARY_TOOL_NAME,
        GET_STUDENT_ATTENDANCE_TOOL_NAME,
        LIST_ROOMS_TOOL_NAME,
        GET_INSTITUTION_MEMBERS_SUMMARY_TOOL_NAME,
    }
)

ADMIN_ONLY_TOOL_NAMES: frozenset[str] = frozenset(
    {
        GET_INSTITUTION_MEMBERS_SUMMARY_TOOL_NAME,
    }
)

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

GET_DASHBOARD_OVERVIEW_DECLARATION: dict[str, Any] = {
    "name": GET_DASHBOARD_OVERVIEW_TOOL_NAME,
    "description": (
        "Consulta métricas consolidadas em tempo real do painel do usuário no Locus: "
        "total de turmas, alunos únicos, taxa média de frequência, total de alunos em risco "
        "(< 75%), resumo de chamadas realizadas nos últimos N dias e última chamada. "
        "Para professores, retorna apenas os dados das suas próprias turmas."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "days": {
                "type": "INTEGER",
                "description": (
                    "Janela em dias para métricas de chamadas (padrão 30, mínimo 1, máximo 365)."
                ),
            },
            "active_only": {
                "type": "BOOLEAN",
                "description": (
                    "Se true, considera apenas turmas ativas; se false, apenas inativas; "
                    "se omitido, considera todas."
                ),
            },
        },
    },
}

LIST_CLASSES_DECLARATION: dict[str, Any] = {
    "name": LIST_CLASSES_TOOL_NAME,
    "description": (
        "Lista turmas cadastradas (com ID, nome, disciplina, sala, quantidade de alunos, "
        "taxa de frequência e se há chamada aberta no momento). "
        "Use esta ferramenta para listar turmas ou resolver o nome de uma turma para seu "
        "`subject_class_id` antes de consultar relatórios ou chamadas de uma turma específica."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "search": {
                "type": "STRING",
                "description": "Texto para filtrar por nome da turma ou disciplina.",
            },
            "active": {
                "type": "BOOLEAN",
                "description": "Filtra por turmas ativas (true) ou inativas (false).",
            },
            "has_active_session": {
                "type": "BOOLEAN",
                "description": "Se true, retorna apenas turmas com chamada aberta agora.",
            },
            "limit": {
                "type": "INTEGER",
                "description": "Máximo de turmas a retornar (padrão 15, máximo 25).",
            },
        },
    },
}

GET_CLASS_ATTENDANCE_REPORT_DECLARATION: dict[str, Any] = {
    "name": GET_CLASS_ATTENDANCE_REPORT_TOOL_NAME,
    "description": (
        "Gera o relatório de frequência em tempo real de uma turma específica: "
        "total de alunos, frequência média da turma, quantidade de alunos em risco (< 75%) "
        "e lista de alunos ordenados da menor para a maior frequência. "
        "Use `list_classes` antes se ainda não tiver o `subject_class_id`."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "subject_class_id": {
                "type": "STRING",
                "description": "UUID da turma (obtido via `list_classes`).",
            },
            "only_at_risk": {
                "type": "BOOLEAN",
                "description": (
                    "Se true, lista apenas alunos em risco de reprovação por falta (< 75%). "
                    "Padrão false."
                ),
            },
            "limit": {
                "type": "INTEGER",
                "description": "Máximo de alunos a listar (padrão 20, máximo 30).",
            },
        },
        "required": ["subject_class_id"],
    },
}

LIST_ATTENDANCE_SESSIONS_DECLARATION: dict[str, Any] = {
    "name": LIST_ATTENDANCE_SESSIONS_TOOL_NAME,
    "description": (
        "Lista sessões de chamada (abertas, encerradas ou canceladas) com turma, sala, "
        "horário de abertura, status e contadores de confirmações/irregulares. "
        "Use `status='OPEN'` para responder se há chamadas abertas agora."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "status": {
                "type": "STRING",
                "description": "Filtra por status da sessão: 'OPEN', 'CLOSED' ou 'CANCELLED'.",
            },
            "subject_class_id": {
                "type": "STRING",
                "description": "UUID opcional de uma turma específica.",
            },
            "search": {
                "type": "STRING",
                "description": "Texto para buscar por nome da turma, disciplina ou código.",
            },
            "days": {
                "type": "INTEGER",
                "description": "Filtra chamadas abertas nos últimos N dias (opcional, 1–365).",
            },
            "limit": {
                "type": "INTEGER",
                "description": "Máximo de sessões a retornar (padrão 15, máximo 25).",
            },
        },
    },
}

GET_SESSION_AUDIT_SUMMARY_DECLARATION: dict[str, Any] = {
    "name": GET_SESSION_AUDIT_SUMMARY_TOOL_NAME,
    "description": (
        "Consulta o resumo de auditoria e lista de presença de uma sessão de chamada específica: "
        "contadores exatos de PRESENTE, IRREGULAR (pendente de auditoria), REJEITADA e AUSENTE, "
        "além dos alunos correspondentes ao filtro opcional. "
        "Use `list_attendance_sessions` antes para obter `subject_class_id` e `session_id`."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "subject_class_id": {
                "type": "STRING",
                "description": "UUID da turma dona da sessão.",
            },
            "session_id": {
                "type": "STRING",
                "description": "UUID da sessão de chamada.",
            },
            "status_filter": {
                "type": "STRING",
                "description": (
                    "Filtro opcional de status dos alunos: "
                    "'PRESENTE', 'IRREGULAR', 'REJEITADA' ou 'AUSENTE'."
                ),
            },
            "limit": {
                "type": "INTEGER",
                "description": "Máximo de alunos a listar (padrão 25, máximo 40).",
            },
        },
        "required": ["subject_class_id", "session_id"],
    },
}

GET_STUDENT_ATTENDANCE_DECLARATION: dict[str, Any] = {
    "name": GET_STUDENT_ATTENDANCE_TOOL_NAME,
    "description": (
        "Busca alunos por nome ou e-mail e retorna seu resumo de frequência "
        "(taxa de presença, presenças, faltas e status). Quando `subject_class_id` também "
        "é informado, enriquece o resultado com os detalhes do aluno naquela turma específica."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "search": {
                "type": "STRING",
                "description": "Nome ou e-mail (total ou parcial) do aluno.",
            },
            "subject_class_id": {
                "type": "STRING",
                "description": "UUID opcional de uma turma específica para detalhar a frequência.",
            },
            "limit": {
                "type": "INTEGER",
                "description": "Máximo de alunos a retornar (padrão 10, máximo 20).",
            },
        },
        "required": ["search"],
    },
}

LIST_ROOMS_DECLARATION: dict[str, Any] = {
    "name": LIST_ROOMS_TOOL_NAME,
    "description": (
        "Lista salas cadastradas na instituição com seu raio de tolerância de geofence "
        "(em metros) e métricas gerais das salas."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "search": {
                "type": "STRING",
                "description": "Texto opcional para filtrar pelo nome da sala.",
            },
            "limit": {
                "type": "INTEGER",
                "description": "Máximo de salas a retornar (padrão 15, máximo 25).",
            },
        },
    },
}

GET_INSTITUTION_MEMBERS_SUMMARY_DECLARATION: dict[str, Any] = {
    "name": GET_INSTITUTION_MEMBERS_SUMMARY_TOOL_NAME,
    "description": (
        "Consulta o resumo administrativo de membros da instituição (professores, coordenadores, "
        "admins e turmas atribuídas) e métricas de convites (pendentes, aceitos, expirados, "
        "revogados e taxa de aceitação). Exclusiva para administradores."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "days": {
                "type": "INTEGER",
                "description": (
                    "Janela em dias para métricas de convites (padrão 30, mínimo 1, máximo 365)."
                ),
            },
        },
    },
}

_COMMON_TOOLS: tuple[dict[str, Any], ...] = (
    SEARCH_LOCUS_DOCS_DECLARATION,
    GET_DASHBOARD_OVERVIEW_DECLARATION,
    LIST_CLASSES_DECLARATION,
    GET_CLASS_ATTENDANCE_REPORT_DECLARATION,
    LIST_ATTENDANCE_SESSIONS_DECLARATION,
    GET_SESSION_AUDIT_SUMMARY_DECLARATION,
    GET_STUDENT_ATTENDANCE_DECLARATION,
    LIST_ROOMS_DECLARATION,
)


def get_assistant_tools(user_role: UserRole | None = None) -> list[dict[str, Any]]:
    """Retorna as declarações de ferramentas disponíveis para o papel do usuário."""
    tools = list(_COMMON_TOOLS)
    if user_role == UserRole.ADMIN:
        tools.append(GET_INSTITUTION_MEMBERS_SUMMARY_DECLARATION)
    return tools


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
