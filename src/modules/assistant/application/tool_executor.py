from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from modules.assistant.domain.tools import (
    ADMIN_ONLY_TOOL_NAMES,
    GET_CLASS_ATTENDANCE_REPORT_TOOL_NAME,
    GET_DASHBOARD_OVERVIEW_TOOL_NAME,
    GET_INSTITUTION_MEMBERS_SUMMARY_TOOL_NAME,
    GET_SESSION_AUDIT_SUMMARY_TOOL_NAME,
    GET_STUDENT_ATTENDANCE_TOOL_NAME,
    LIST_ATTENDANCE_SESSIONS_TOOL_NAME,
    LIST_CLASSES_TOOL_NAME,
    LIST_ROOMS_TOOL_NAME,
)
from modules.attendance.application.use_cases.get_attendance_metrics import (
    GetAttendanceMetricsInput,
    GetAttendanceMetricsUseCase,
)
from modules.attendance.application.use_cases.get_session import (
    GetAttendanceSessionInput,
    GetAttendanceSessionUseCase,
)
from modules.attendance.application.use_cases.list_session_roster import (
    ListSessionRosterInput,
    ListSessionRosterUseCase,
)
from modules.attendance.application.use_cases.list_tenant_sessions import (
    ListTenantAttendanceSessionsInput,
    ListTenantAttendanceSessionsUseCase,
)
from modules.attendance.domain.entities.session_roster_item import SessionRosterItem
from modules.report.application.use_cases.generate_class_report import (
    GenerateClassReportInput,
    GenerateClassReportUseCase,
)
from modules.report.application.use_cases.get_dashboard_metrics import (
    GetDashboardMetricsInput,
    GetDashboardMetricsUseCase,
)
from modules.report.application.use_cases.get_student_report import (
    GetStudentReportInput,
    GetStudentReportUseCase,
)
from modules.room.application.use_cases.get_room_metrics import (
    GetRoomMetricsInput,
    GetRoomMetricsUseCase,
)
from modules.room.application.use_cases.list_rooms import (
    ListRoomsInput,
    ListRoomsUseCase,
)
from modules.subject_class.application.use_cases.list_subject_classes import (
    ListSubjectClassesInput,
    ListSubjectClassesUseCase,
)
from modules.subject_class.domain.entities.subject_class import SubjectClass
from modules.subject_class.domain.repositories.subject_class_repository import (
    SubjectClassRepository,
)
from modules.tenant.application.use_cases.get_members_metrics import (
    GetMembersMetricsInput,
    GetMembersMetricsUseCase,
)
from modules.tenant.application.use_cases.get_tenant_invites_metrics import (
    GetTenantInvitesMetricsInput,
    GetTenantInvitesMetricsUseCase,
)
from modules.tenant.application.use_cases.list_students import (
    ListStudentsInput,
    ListStudentsUseCase,
)
from modules.tenant.domain.repositories.tenant_repository import TenantMemberRepository
from shared.enums.record_status import RecordStatus
from shared.enums.session_status import SessionStatus
from shared.enums.user_role import UserRole
from shared.exceptions import (
    BusinessRuleException,
    ForbiddenException,
    ResourceNotFoundException,
)
from shared.pagination import PaginationParams

_ROSTER_STATUS_ALIASES: dict[str, str] = {
    "PRESENTE": "PRESENTE",
    "REGULAR": "PRESENTE",
    "APPROVED": "PRESENTE",
    "APROVADA": "PRESENTE",
    "IRREGULAR": "IRREGULAR",
    "REJEITADA": "REJEITADA",
    "REJECTED": "REJEITADA",
    "AUSENTE": "AUSENTE",
    "ABSENT": "AUSENTE",
}

_SESSION_STATUS_ALIASES: dict[str, SessionStatus] = {
    "OPEN": SessionStatus.OPEN,
    "ABERTA": SessionStatus.OPEN,
    "CLOSED": SessionStatus.CLOSED,
    "ENCERRADA": SessionStatus.CLOSED,
    "CANCELLED": SessionStatus.CANCELLED,
    "CANCELED": SessionStatus.CANCELLED,
    "CANCELADA": SessionStatus.CANCELLED,
}


@dataclass(frozen=True)
class ToolExecutionContext:
    """Contexto autenticado injetado exclusivamente pelo servidor (nunca pelo LLM)."""

    tenant_id: UUID
    user_id: UUID
    user_role: UserRole


class AssistantToolExecutor:
    """Despacha e executa ferramentas read-only de dados operacionais do Locus com isolamento por papel."""

    def __init__(
        self,
        *,
        get_dashboard_metrics: GetDashboardMetricsUseCase,
        get_attendance_metrics: GetAttendanceMetricsUseCase,
        list_subject_classes: ListSubjectClassesUseCase,
        generate_class_report: GenerateClassReportUseCase,
        list_tenant_sessions: ListTenantAttendanceSessionsUseCase,
        get_session: GetAttendanceSessionUseCase,
        list_session_roster: ListSessionRosterUseCase,
        list_students: ListStudentsUseCase,
        get_student_report: GetStudentReportUseCase,
        list_rooms: ListRoomsUseCase,
        get_room_metrics: GetRoomMetricsUseCase,
        get_members_metrics: GetMembersMetricsUseCase,
        get_tenant_invites_metrics: GetTenantInvitesMetricsUseCase,
        subject_class_repo: SubjectClassRepository,
        member_repo: TenantMemberRepository,
    ) -> None:
        self._get_dashboard_metrics = get_dashboard_metrics
        self._get_attendance_metrics = get_attendance_metrics
        self._list_subject_classes = list_subject_classes
        self._generate_class_report = generate_class_report
        self._list_tenant_sessions = list_tenant_sessions
        self._get_session = get_session
        self._list_session_roster = list_session_roster
        self._list_students = list_students
        self._get_student_report = get_student_report
        self._list_rooms = list_rooms
        self._get_room_metrics = get_room_metrics
        self._get_members_metrics = get_members_metrics
        self._get_tenant_invites_metrics = get_tenant_invites_metrics
        self._subject_class_repo = subject_class_repo
        self._member_repo = member_repo

    async def execute(
        self,
        *,
        ctx: ToolExecutionContext,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> str:
        """Executa uma ferramenta operacional retornando texto formatado em pt-BR."""
        if tool_name in ADMIN_ONLY_TOOL_NAMES and ctx.user_role != UserRole.ADMIN:
            return (
                "Acesso negado: esta consulta é restrita a administradores (ADMIN) da instituição."
            )

        handlers = {
            GET_DASHBOARD_OVERVIEW_TOOL_NAME: self._handle_dashboard_overview,
            LIST_CLASSES_TOOL_NAME: self._handle_list_classes,
            GET_CLASS_ATTENDANCE_REPORT_TOOL_NAME: self._handle_class_attendance_report,
            LIST_ATTENDANCE_SESSIONS_TOOL_NAME: self._handle_list_attendance_sessions,
            GET_SESSION_AUDIT_SUMMARY_TOOL_NAME: self._handle_session_audit_summary,
            GET_STUDENT_ATTENDANCE_TOOL_NAME: self._handle_student_attendance,
            LIST_ROOMS_TOOL_NAME: self._handle_list_rooms,
            GET_INSTITUTION_MEMBERS_SUMMARY_TOOL_NAME: self._handle_institution_members_summary,
        }
        handler = handlers.get(tool_name)
        if handler is None:
            return f"Ferramenta '{tool_name}' não suportada."

        try:
            return await handler(ctx, arguments)
        except (ValueError, ResourceNotFoundException, ForbiddenException, BusinessRuleException) as exc:
            return str(exc)

    async def _assert_can_access_class(
        self,
        *,
        ctx: ToolExecutionContext,
        subject_class_id: UUID,
    ) -> SubjectClass:
        """Garante que a turma existe na tenant e, se o usuário for PROFESSOR, pertence a ele."""
        subject_class = await self._subject_class_repo.find_by_id_and_tenant(
            subject_class_id, ctx.tenant_id
        )
        if not subject_class or getattr(subject_class, "deleted", False):
            raise ResourceNotFoundException("Turma não encontrada nesta instituição.")

        if ctx.user_role == UserRole.PROFESSOR:
            member = await self._member_repo.find_by_tenant_and_user(
                tenant_id=ctx.tenant_id,
                user_id=ctx.user_id,
            )
            if not member or member.deleted or subject_class.professor_id != member.id:
                raise ForbiddenException(
                    "Acesso negado: você só pode consultar dados das suas próprias turmas."
                )

        return subject_class

    async def _handle_dashboard_overview(
        self, ctx: ToolExecutionContext, args: dict[str, Any]
    ) -> str:
        days = self._parse_int(args.get("days"), default=30, minimum=1, maximum=365)
        active_only = self._parse_optional_bool(args.get("active_only"))

        dashboard = await self._get_dashboard_metrics.execute(
            GetDashboardMetricsInput(
                tenant_id=ctx.tenant_id,
                user_id=ctx.user_id,
                user_role=ctx.user_role,
                active=active_only,
            )
        )
        attendance = await self._get_attendance_metrics.execute(
            GetAttendanceMetricsInput(
                tenant_id=ctx.tenant_id,
                user_id=ctx.user_id,
                user_role=ctx.user_role,
                days=days,
            )
        )

        lines = [
            "Resumo operacional do painel (/dashboard):",
            f"- Total de turmas: {dashboard.total_classes}",
            f"- Alunos únicos: {dashboard.total_unique_students}",
            f"- Taxa média de frequência geral: {self._fmt_pct(dashboard.average_attendance_rate)}",
            f"- Alunos em risco (< 75%): {dashboard.total_students_at_risk}",
            f"- Chamadas nos últimos {days} dias: {attendance.get('total_sessions', 0)} "
            f"(canceladas: {attendance.get('cancelled_sessions', 0)}, "
            f"frequência média no período: "
            f"{self._fmt_pct(float(attendance.get('average_attendance_rate', 0.0)))})",
        ]

        last_session = attendance.get("last_session")
        if isinstance(last_session, dict):
            lines.append(
                f"- Última chamada: {last_session.get('subject_class_name', 'Turma')} "
                f"(status: {getattr(last_session.get('status'), 'value', last_session.get('status'))}, "
                f"confirmados: {last_session.get('confirmed_count', 0)}/{last_session.get('total_students', 0)}, "
                f"rota: /dashboard/chamadas/{last_session.get('id')})"
            )

        if dashboard.at_risk_students:
            lines.append("- Alunos em risco em destaque:")
            for item in dashboard.at_risk_students[:5]:
                level = "crítico" if item.critical else "alerta"
                lines.append(
                    f"  • {item.student_name} ({item.class_name}): "
                    f"{self._fmt_pct(item.attendance_rate)} — {item.absences} faltas [{level}]"
                )

        return "\n".join(lines)

    async def _handle_list_classes(self, ctx: ToolExecutionContext, args: dict[str, Any]) -> str:
        search = self._parse_optional_str(args.get("search"))
        active = self._parse_optional_bool(args.get("active"))
        has_active_session = self._parse_optional_bool(args.get("has_active_session"))
        limit = self._parse_int(args.get("limit"), default=15, minimum=1, maximum=25)

        page = await self._list_subject_classes.execute(
            ListSubjectClassesInput(
                tenant_id=ctx.tenant_id,
                pagination=PaginationParams(page=1, page_size=limit),
                search=search,
                active=active,
                has_active_session=has_active_session,
                user_id=ctx.user_id,
                user_role=ctx.user_role,
            )
        )

        if not page.items:
            return "Nenhuma turma encontrada com os filtros informados (/dashboard/turmas)."

        lines = [
            f"Turmas encontradas: exibindo {len(page.items)} de {page.total} (/dashboard/turmas):"
        ]
        for item in page.items:
            status_label = "ativa" if item.active else "inativa"
            room_label = item.room_name or "sem sala"
            session_label = (
                f"chamada ABERTA (/dashboard/chamadas/{item.active_session_id})"
                if item.has_active_session and item.active_session_id
                else "sem chamada aberta"
            )
            lines.append(
                f"- {item.name} ({item.discipline_name}) | ID: {item.id} | {status_label} | "
                f"sala: {room_label} | alunos: {item.student_count} | "
                f"frequência: {self._fmt_pct(item.attendance_rate)} | {session_label} | "
                f"rota: /dashboard/turmas/{item.id}"
            )
        if page.total > len(page.items):
            lines.append(
                f"(Mostrando apenas as primeiras {len(page.items)} de {page.total} turmas.)"
            )
        return "\n".join(lines)

    async def _handle_class_attendance_report(
        self, ctx: ToolExecutionContext, args: dict[str, Any]
    ) -> str:
        subject_class_id = self._parse_uuid(args.get("subject_class_id"), "subject_class_id")
        only_at_risk = bool(self._parse_optional_bool(args.get("only_at_risk")) or False)
        limit = self._parse_int(args.get("limit"), default=20, minimum=1, maximum=30)

        subject_class = await self._assert_can_access_class(
            ctx=ctx, subject_class_id=subject_class_id
        )
        report = await self._generate_class_report.execute(
            GenerateClassReportInput(
                tenant_id=ctx.tenant_id,
                subject_class_id=subject_class_id,
            )
        )

        filtered = (
            [s for s in report.students if s.at_risk] if only_at_risk else list(report.students)
        )
        shown = filtered[:limit]

        lines = [
            f"Relatório de frequência da turma '{subject_class.name}' "
            f"({subject_class.discipline_name}) — rota: /dashboard/turmas/{subject_class_id}",
            f"- Total de alunos: {report.total_students}",
            f"- Frequência média da turma: {self._fmt_pct(report.class_average_frequency)}",
            f"- Alunos em risco (< 75%): {report.students_at_risk}",
        ]

        if not shown:
            if only_at_risk:
                lines.append("- Nenhum aluno está abaixo do limite de frequência nesta turma.")
            else:
                lines.append("- Nenhum aluno matriculado com registros nesta turma.")
            return "\n".join(lines)

        heading = (
            f"- Alunos em risco (exibindo {len(shown)} de {len(filtered)}):"
            if only_at_risk
            else f"- Alunos ordenados da menor para a maior frequência (exibindo {len(shown)} de {len(filtered)}):"
        )
        lines.append(heading)
        for student in shown:
            risk_tag = " [EM RISCO]" if student.at_risk else ""
            lines.append(
                f"  • {student.student_name}: {self._fmt_pct(student.frequency_rate)} "
                f"(presenças: {student.total_present}, faltas: {student.total_absent}, "
                f"irregulares: {student.total_irregular}){risk_tag}"
            )
        if len(filtered) > len(shown):
            lines.append(
                f"(Lista truncada em {len(shown)} de {len(filtered)} alunos para manter o resumo objetivo.)"
            )
        return "\n".join(lines)

    async def _handle_list_attendance_sessions(
        self, ctx: ToolExecutionContext, args: dict[str, Any]
    ) -> str:
        raw_status = self._parse_optional_str(args.get("status"))
        status_enum = self._parse_session_status(raw_status) if raw_status else None
        raw_class_id = self._parse_optional_str(args.get("subject_class_id"))
        subject_class_id = (
            self._parse_uuid(raw_class_id, "subject_class_id") if raw_class_id else None
        )
        search = self._parse_optional_str(args.get("search"))
        days = (
            self._parse_int(args.get("days"), default=30, minimum=1, maximum=365)
            if args.get("days") is not None
            else None
        )
        limit = self._parse_int(args.get("limit"), default=15, minimum=1, maximum=25)

        opened_after = (datetime.now(UTC) - timedelta(days=days)) if days is not None else None

        page = await self._list_tenant_sessions.execute(
            ListTenantAttendanceSessionsInput(
                tenant_id=ctx.tenant_id,
                user_id=ctx.user_id,
                user_role=ctx.user_role,
                pagination=PaginationParams(page=1, page_size=limit),
                subject_class_id=subject_class_id,
                status=status_enum,
                opened_after=opened_after,
                search=search,
            )
        )

        if not page.items:
            return "Nenhuma sessão de chamada encontrada com os filtros informados (/dashboard/chamadas)."

        lines = [
            f"Sessões de chamada encontradas: exibindo {len(page.items)} de {page.total} "
            f"(/dashboard/chamadas):"
        ]
        for s in page.items:
            class_name = s.subject_class.name if s.subject_class else str(s.subject_class_id)
            room_name = s.room.name if s.room else "sem sala"
            opened_str = s.opened_at.strftime("%d/%m/%Y %H:%M UTC")
            lines.append(
                f"- Sessão {s.id} | Turma: {class_name} (subject_class_id: {s.subject_class_id}) | "
                f"Status: {s.status.value} | Aberta em: {opened_str} | Sala: {room_name} | "
                f"Confirmados: {s.confirmed_count}/{s.total_students} | "
                f"Irregulares: {s.irregular_count} | rota: /dashboard/chamadas/{s.id}"
            )
        if page.total > len(page.items):
            lines.append(
                f"(Mostrando apenas as primeiras {len(page.items)} de {page.total} sessões.)"
            )
        return "\n".join(lines)

    async def _handle_session_audit_summary(
        self, ctx: ToolExecutionContext, args: dict[str, Any]
    ) -> str:
        subject_class_id = self._parse_uuid(args.get("subject_class_id"), "subject_class_id")
        session_id = self._parse_uuid(args.get("session_id"), "session_id")
        raw_filter = self._parse_optional_str(args.get("status_filter"))
        status_filter = self._normalize_roster_status(raw_filter) if raw_filter else None
        limit = self._parse_int(args.get("limit"), default=25, minimum=1, maximum=40)

        subject_class = await self._assert_can_access_class(
            ctx=ctx, subject_class_id=subject_class_id
        )
        session = await self._get_session.execute(
            GetAttendanceSessionInput(
                tenant_id=ctx.tenant_id,
                subject_class_id=subject_class_id,
                session_id=session_id,
            )
        )
        roster = await self._list_session_roster.execute(
            ListSessionRosterInput(
                tenant_id=ctx.tenant_id,
                subject_class_id=subject_class_id,
                session_id=session_id,
            )
        )

        counts: dict[str, int] = {
            "PRESENTE": 0,
            "IRREGULAR": 0,
            "REJEITADA": 0,
            "AUSENTE": 0,
        }
        classified: list[tuple[SessionRosterItem, str]] = []
        for item in roster:
            bucket = self._classify_roster_item(item)
            counts[bucket] += 1
            classified.append((item, bucket))

        filtered = (
            [(item, b) for item, b in classified if b == status_filter]
            if status_filter is not None
            else classified
        )
        shown = filtered[:limit]

        opened_str = session.opened_at.strftime("%d/%m/%Y %H:%M UTC")
        lines = [
            f"Auditoria da chamada {session.id} — Turma '{subject_class.name}' "
            f"(status: {session.status.value}, aberta em: {opened_str}) — "
            f"rota: /dashboard/chamadas/{session.id}",
            f"- Total de matriculados: {len(roster)}",
            f"- PRESENTE: {counts['PRESENTE']} | IRREGULAR (pendente de auditoria): {counts['IRREGULAR']} | "
            f"REJEITADA: {counts['REJEITADA']} | AUSENTE: {counts['AUSENTE']}",
        ]

        if not shown:
            if status_filter:
                lines.append(f"- Nenhum aluno com status '{status_filter}' nesta chamada.")
            else:
                lines.append("- Nenhum aluno matriculado nesta chamada.")
            return "\n".join(lines)

        filter_label = f" (filtro: {status_filter})" if status_filter else ""
        lines.append(f"- Detalhes{filter_label} — exibindo {len(shown)} de {len(filtered)}:")
        for item, bucket in shown:
            distance_info = (
                f", distância: {item.distance_meters:.1f}m"
                if item.distance_meters is not None
                else ""
            )
            lines.append(f"  • {item.student_name}: {bucket}{distance_info}")
        if len(filtered) > len(shown):
            lines.append(
                f"(Lista truncada em {len(shown)} de {len(filtered)} alunos.)"
            )
        return "\n".join(lines)

    async def _handle_student_attendance(
        self, ctx: ToolExecutionContext, args: dict[str, Any]
    ) -> str:
        search = self._parse_optional_str(args.get("search"))
        if not search:
            raise ValueError("Informe o nome ou e-mail do aluno no parâmetro 'search'.")

        raw_class_id = self._parse_optional_str(args.get("subject_class_id"))
        subject_class_id = (
            self._parse_uuid(raw_class_id, "subject_class_id") if raw_class_id else None
        )
        limit = self._parse_int(args.get("limit"), default=10, minimum=1, maximum=20)

        subject_class: SubjectClass | None = None
        if subject_class_id is not None:
            subject_class = await self._assert_can_access_class(
                ctx=ctx, subject_class_id=subject_class_id
            )

        professor_user_id = ctx.user_id if ctx.user_role == UserRole.PROFESSOR else None
        page = await self._list_students.execute(
            ListStudentsInput(
                tenant_id=ctx.tenant_id,
                pagination=PaginationParams(page=1, page_size=limit),
                search=search,
                subject_class_id=subject_class_id,
                professor_user_id=professor_user_id,
            )
        )

        if not page.items:
            return f"Nenhum aluno encontrado para a busca '{search}' (/dashboard/alunos)."

        header = (
            f"Frequência de alunos na turma '{subject_class.name}' para '{search}'"
            if subject_class is not None
            else f"Resumo de frequência de alunos encontrados para '{search}'"
        )
        lines = [f"{header} (exibindo {len(page.items)} de {page.total}, rota: /dashboard/alunos):"]

        for idx, member in enumerate(page.items):
            if subject_class_id is not None and idx < 5:
                try:
                    student_report = await self._get_student_report.execute(
                        GetStudentReportInput(
                            tenant_id=ctx.tenant_id,
                            subject_class_id=subject_class_id,
                            tenant_member_id=member.id,
                        )
                    )
                    risk_tag = " [EM RISCO]" if student_report.at_risk else ""
                    lines.append(
                        f"- {student_report.student_name}: "
                        f"{self._fmt_pct(student_report.frequency_rate)} na turma "
                        f"(presenças: {student_report.total_present}, "
                        f"faltas: {student_report.total_absent}, "
                        f"irregulares: {student_report.total_irregular}){risk_tag}"
                    )
                    continue
                except ResourceNotFoundException:
                    pass

            lines.append(
                f"- {member.name}: frequência geral {self._fmt_pct(member.attendance_rate)} | "
                f"turmas: {member.turmas_count} | presenças: {member.total_present} | "
                f"faltas: {member.total_absent} | sessões: {member.total_sessions} | "
                f"status: {member.status}"
            )

        if page.total > len(page.items):
            lines.append(
                f"(Mostrando apenas os primeiros {len(page.items)} de {page.total} alunos.)"
            )
        return "\n".join(lines)

    async def _handle_list_rooms(self, ctx: ToolExecutionContext, args: dict[str, Any]) -> str:
        search = self._parse_optional_str(args.get("search"))
        limit = self._parse_int(args.get("limit"), default=15, minimum=1, maximum=25)

        page = await self._list_rooms.execute(
            ListRoomsInput(
                tenant_id=ctx.tenant_id,
                pagination=PaginationParams(page=1, page_size=limit),
                search=search,
            )
        )
        metrics = await self._get_room_metrics.execute(
            GetRoomMetricsInput(tenant_id=ctx.tenant_id)
        )

        lines = [
            f"Salas cadastradas (/dashboard/salas) — total na instituição: {metrics.total_rooms}, "
            f"raio médio: {metrics.avg_radius}m "
            f"(precisas: {metrics.precisas_count}, amplas: {metrics.amplas_count}):"
        ]
        if not page.items:
            lines.append("- Nenhuma sala encontrada com o filtro informado.")
            return "\n".join(lines)

        for room in page.items:
            lines.append(
                f"- {room.name} | ID: {room.id} | raio de geofence: {room.tolerance_radius_meters}m"
            )
        if page.total > len(page.items):
            lines.append(
                f"(Mostrando apenas as primeiras {len(page.items)} de {page.total} salas.)"
            )
        return "\n".join(lines)

    async def _handle_institution_members_summary(
        self, ctx: ToolExecutionContext, args: dict[str, Any]
    ) -> str:
        days = self._parse_int(args.get("days"), default=30, minimum=1, maximum=365)

        members = await self._get_members_metrics.execute(
            GetMembersMetricsInput(tenant_id=ctx.tenant_id)
        )
        invites = await self._get_tenant_invites_metrics.execute(
            GetTenantInvitesMetricsInput(tenant_id=ctx.tenant_id, days=days)
        )

        lines = [
            "Resumo administrativo de membros e convites (/dashboard/membros e /dashboard/convites):",
            f"- Total de membros da equipe: {members.total_members}",
            f"- Professores: {members.professors_count} | Coordenadores: {members.coordinators_count} | "
            f"Admins: {members.admins_count}",
            f"- Turmas atribuídas: {members.assigned_classes_count}",
            f"- Convites nos últimos {invites.days} dias: total {invites.total} "
            f"(pendentes: {invites.pending}, aceitos: {invites.accepted}, "
            f"expirados: {invites.expired}, revogados: {invites.revoked}, "
            f"taxa de aceitação: {self._fmt_pct(invites.acceptance_rate)})",
        ]
        return "\n".join(lines)

    @staticmethod
    def _classify_roster_item(item: SessionRosterItem) -> str:
        if item.record_status is None:
            return "AUSENTE"
        if item.record_status in (RecordStatus.REGULAR, RecordStatus.APPROVED):
            return "PRESENTE"
        if item.record_status == RecordStatus.IRREGULAR:
            return "IRREGULAR"
        if item.record_status == RecordStatus.REJECTED:
            return "REJEITADA"
        return "AUSENTE"

    @staticmethod
    def _normalize_roster_status(raw: str) -> str:
        normalized = _ROSTER_STATUS_ALIASES.get(raw.strip().upper())
        if normalized is None:
            raise ValueError(
                f"Filtro de status inválido: '{raw}'. Use PRESENTE, IRREGULAR, REJEITADA ou AUSENTE."
            )
        return normalized

    @staticmethod
    def _parse_session_status(raw: str) -> SessionStatus:
        parsed = _SESSION_STATUS_ALIASES.get(raw.strip().upper())
        if parsed is None:
            raise ValueError(
                f"Status de sessão inválido: '{raw}'. Use OPEN, CLOSED ou CANCELLED."
            )
        return parsed

    @staticmethod
    def _parse_uuid(value: Any, field_name: str) -> UUID:
        if value is None or not str(value).strip():
            raise ValueError(f"Parâmetro obrigatório '{field_name}' não informado.")
        try:
            return UUID(str(value).strip())
        except ValueError as exc:
            raise ValueError(
                f"O parâmetro '{field_name}' deve ser um UUID válido. "
                "Use `list_classes` ou `list_attendance_sessions` para obter o ID correto."
            ) from exc

    @staticmethod
    def _parse_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
        if value is None:
            return default
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return default
        return max(minimum, min(maximum, parsed))

    @staticmethod
    def _parse_optional_bool(value: Any) -> bool | None:
        if value is None:
            return None
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in ("true", "1", "sim", "yes"):
                return True
            if lowered in ("false", "0", "nao", "não", "no"):
                return False
        return None

    @staticmethod
    def _parse_optional_str(value: Any) -> str | None:
        if value is None:
            return None
        cleaned = str(value).strip()
        return cleaned if cleaned else None

    @staticmethod
    def _fmt_pct(rate: float) -> str:
        pct = rate * 100 if rate <= 1.0 else rate
        return f"{pct:.1f}%"

