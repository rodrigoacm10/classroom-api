from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from modules.assistant.application.tool_executor import (
    AssistantToolExecutor,
    ToolExecutionContext,
)
from modules.assistant.domain.tools import (
    GET_CLASS_ATTENDANCE_REPORT_TOOL_NAME,
    GET_DASHBOARD_OVERVIEW_TOOL_NAME,
    GET_INSTITUTION_MEMBERS_SUMMARY_TOOL_NAME,
    GET_SESSION_AUDIT_SUMMARY_TOOL_NAME,
    GET_STUDENT_ATTENDANCE_TOOL_NAME,
    LIST_ATTENDANCE_SESSIONS_TOOL_NAME,
    LIST_CLASSES_TOOL_NAME,
    LIST_ROOMS_TOOL_NAME,
    get_assistant_tools,
)
from modules.attendance.domain.entities.attendance_session import (
    AttendanceSession,
    RoomInfo,
    SubjectClassInfo,
)
from modules.attendance.domain.entities.session_roster_item import SessionRosterItem
from modules.report.domain.entities.class_report import ClassReport
from modules.report.domain.entities.dashboard_metrics import (
    AtRiskStudentMetric,
    DashboardMetrics,
)
from modules.report.domain.entities.student_report import StudentReport
from modules.room.domain.entities.room import Room
from modules.room.domain.entities.room_metrics import RoomMetrics
from modules.subject_class.domain.entities.subject_class import SubjectClass
from modules.subject_class.domain.entities.subject_class_summary import SubjectClassSummary
from modules.tenant.domain.entities.members_metrics import MembersMetrics
from modules.tenant.domain.entities.tenant_invite import TenantInvitesMetrics
from modules.tenant.domain.entities.tenant_member import TenantMember
from shared.enums.record_status import RecordStatus
from shared.enums.session_status import SessionStatus
from shared.enums.user_role import UserRole
from shared.pagination import Page


def _build_executor() -> tuple[AssistantToolExecutor, dict[str, Any]]:
    mocks: dict[str, Any] = {
        "get_dashboard_metrics": AsyncMock(),
        "get_attendance_metrics": AsyncMock(),
        "list_subject_classes": AsyncMock(),
        "generate_class_report": AsyncMock(),
        "list_tenant_sessions": AsyncMock(),
        "get_session": AsyncMock(),
        "list_session_roster": AsyncMock(),
        "list_students": AsyncMock(),
        "get_student_report": AsyncMock(),
        "list_rooms": AsyncMock(),
        "get_room_metrics": AsyncMock(),
        "get_members_metrics": AsyncMock(),
        "get_tenant_invites_metrics": AsyncMock(),
        "subject_class_repo": AsyncMock(),
        "member_repo": AsyncMock(),
    }
    executor = AssistantToolExecutor(**mocks)
    return executor, mocks


class TestAssistantToolDeclarations:
    def test_admin_receives_all_nine_tools_while_lower_roles_exclude_admin_only_tools(
        self,
    ) -> None:
        admin_names = {t["name"] for t in get_assistant_tools(UserRole.ADMIN)}
        coord_names = {t["name"] for t in get_assistant_tools(UserRole.COORDENADOR)}
        prof_names = {t["name"] for t in get_assistant_tools(UserRole.PROFESSOR)}

        assert len(admin_names) == 9
        assert GET_INSTITUTION_MEMBERS_SUMMARY_TOOL_NAME in admin_names

        assert len(coord_names) == 8
        assert GET_INSTITUTION_MEMBERS_SUMMARY_TOOL_NAME not in coord_names

        assert len(prof_names) == 8
        assert GET_INSTITUTION_MEMBERS_SUMMARY_TOOL_NAME not in prof_names


class TestAssistantToolExecutor:
    @pytest.mark.parametrize("role", [UserRole.PROFESSOR, UserRole.COORDENADOR])
    async def test_blocks_admin_only_tool_at_runtime_for_non_admin_roles(
        self, role: UserRole
    ) -> None:
        executor, mocks = _build_executor()
        ctx = ToolExecutionContext(tenant_id=uuid4(), user_id=uuid4(), user_role=role)

        result = await executor.execute(
            ctx=ctx,
            tool_name=GET_INSTITUTION_MEMBERS_SUMMARY_TOOL_NAME,
            arguments={"days": 30},
        )

        assert "Acesso negado" in result
        mocks["get_members_metrics"].execute.assert_not_awaited()
        mocks["get_tenant_invites_metrics"].execute.assert_not_awaited()

    async def test_admin_can_query_institution_members_and_invites_summary(self) -> None:
        executor, mocks = _build_executor()
        ctx = ToolExecutionContext(tenant_id=uuid4(), user_id=uuid4(), user_role=UserRole.ADMIN)

        mocks["get_members_metrics"].execute.return_value = MembersMetrics(
            total_members=18,
            professors_count=12,
            coordinators_count=4,
            admins_count=2,
            management_count=6,
            assigned_classes_count=24,
        )
        mocks["get_tenant_invites_metrics"].execute.return_value = TenantInvitesMetrics(
            total=10,
            pending=3,
            accepted=5,
            expired=1,
            revoked=1,
            acceptance_rate=0.5,
            days=30,
        )

        result = await executor.execute(
            ctx=ctx,
            tool_name=GET_INSTITUTION_MEMBERS_SUMMARY_TOOL_NAME,
            arguments={"days": 30},
        )

        assert "Professores: 12" in result
        assert "pendentes: 3" in result
        assert "50.0%" in result

    async def test_dashboard_overview_combines_dashboard_and_attendance_metrics(self) -> None:
        executor, mocks = _build_executor()
        ctx = ToolExecutionContext(
            tenant_id=uuid4(), user_id=uuid4(), user_role=UserRole.PROFESSOR
        )

        mocks["get_dashboard_metrics"].execute.return_value = DashboardMetrics(
            total_classes=3,
            total_unique_students=85,
            average_attendance_rate=0.84,
            total_students_at_risk=4,
            at_risk_students=[
                AtRiskStudentMetric(
                    enrollment_id=uuid4(),
                    student_name="Carlos Lima",
                    class_name="Física I",
                    total_sessions=10,
                    absences=4,
                    attendance_rate=0.60,
                    critical=True,
                )
            ],
        )
        mocks["get_attendance_metrics"].execute.return_value = {
            "total_sessions": 12,
            "cancelled_sessions": 1,
            "average_attendance_rate": 0.86,
            "last_session": None,
        }

        result = await executor.execute(
            ctx=ctx,
            tool_name=GET_DASHBOARD_OVERVIEW_TOOL_NAME,
            arguments={"days": 15, "active_only": True},
        )

        assert "Total de turmas: 3" in result
        assert "84.0%" in result
        assert "Carlos Lima" in result
        assert "Chamadas nos últimos 15 dias: 12" in result

    async def test_list_classes_injects_context_and_formats_routes(self) -> None:
        executor, mocks = _build_executor()
        tenant_id = uuid4()
        class_id = uuid4()
        session_id = uuid4()
        ctx = ToolExecutionContext(
            tenant_id=tenant_id, user_id=uuid4(), user_role=UserRole.PROFESSOR
        )

        now = datetime.now(UTC)
        mocks["list_subject_classes"].execute.return_value = Page(
            items=[
                SubjectClassSummary(
                    id=class_id,
                    tenant_id=tenant_id,
                    professor_id=uuid4(),
                    professor_name="Prof. Ana",
                    room_id=uuid4(),
                    name="Física I - Turma A",
                    discipline_name="Física",
                    student_count=32,
                    attendance_rate=0.88,
                    created_at=now,
                    updated_at=now,
                    active=True,
                    room_name="Sala 102",
                    has_active_session=True,
                    active_session_id=session_id,
                )
            ],
            total=1,
            page=1,
            page_size=15,
        )

        result = await executor.execute(
            ctx=ctx,
            tool_name=LIST_CLASSES_TOOL_NAME,
            arguments={"search": "Física", "active": True},
        )

        assert "Física I - Turma A" in result
        assert str(class_id) in result
        assert f"/dashboard/chamadas/{session_id}" in result
        call_input = mocks["list_subject_classes"].execute.call_args.args[0]
        assert call_input.tenant_id == tenant_id
        assert call_input.user_id == ctx.user_id
        assert call_input.user_role == UserRole.PROFESSOR

    async def test_class_report_blocks_professor_who_does_not_own_class(self) -> None:
        executor, mocks = _build_executor()
        tenant_id = uuid4()
        class_id = uuid4()
        owner_member_id = uuid4()
        other_member_id = uuid4()
        ctx = ToolExecutionContext(
            tenant_id=tenant_id, user_id=uuid4(), user_role=UserRole.PROFESSOR
        )

        mocks["subject_class_repo"].find_by_id_and_tenant.return_value = SubjectClass(
            id=class_id,
            tenant_id=tenant_id,
            professor_id=owner_member_id,
            name="Química",
            discipline_name="Química Geral",
        )
        mocks["member_repo"].find_by_tenant_and_user.return_value = TenantMember(
            id=other_member_id,
            tenant_id=tenant_id,
            user_id=ctx.user_id,
            role=UserRole.PROFESSOR,
        )

        result = await executor.execute(
            ctx=ctx,
            tool_name=GET_CLASS_ATTENDANCE_REPORT_TOOL_NAME,
            arguments={"subject_class_id": str(class_id)},
        )

        assert "Acesso negado" in result
        mocks["generate_class_report"].execute.assert_not_awaited()

    async def test_class_report_filters_only_at_risk_and_caps_rows_with_exact_totals(
        self,
    ) -> None:
        executor, mocks = _build_executor()
        tenant_id = uuid4()
        class_id = uuid4()
        prof_member_id = uuid4()
        ctx = ToolExecutionContext(
            tenant_id=tenant_id, user_id=uuid4(), user_role=UserRole.PROFESSOR
        )

        mocks["subject_class_repo"].find_by_id_and_tenant.return_value = SubjectClass(
            id=class_id,
            tenant_id=tenant_id,
            professor_id=prof_member_id,
            name="Física I",
            discipline_name="Física",
        )
        mocks["member_repo"].find_by_tenant_and_user.return_value = TenantMember(
            id=prof_member_id,
            tenant_id=tenant_id,
            user_id=ctx.user_id,
            role=UserRole.PROFESSOR,
        )
        mocks["generate_class_report"].execute.return_value = ClassReport(
            subject_class_id=class_id,
            total_students=4,
            class_average_frequency=0.72,
            students_at_risk=3,
            students=[
                StudentReport(uuid4(), "Aluno 1", 5, 5, 0, 0.50, True, 10.0, 0),
                StudentReport(uuid4(), "Aluno 2", 6, 4, 0, 0.60, True, 12.0, 0),
                StudentReport(uuid4(), "Aluno 3", 7, 3, 0, 0.70, True, 8.0, 0),
                StudentReport(uuid4(), "Aluno Seguro", 9, 1, 0, 0.90, False, 5.0, 0),
            ],
            strategy_used="sequential",
            workers_used=1,
            duration_ms=2.5,
        )

        result = await executor.execute(
            ctx=ctx,
            tool_name=GET_CLASS_ATTENDANCE_REPORT_TOOL_NAME,
            arguments={"subject_class_id": str(class_id), "only_at_risk": True, "limit": 2},
        )

        assert "Total de alunos: 4" in result
        assert "Alunos em risco (< 75%): 3" in result
        assert "Aluno 1" in result
        assert "Aluno 2" in result
        assert "Aluno 3" not in result  # truncated by limit=2
        assert "Aluno Seguro" not in result  # filtered out by only_at_risk=True
        assert "truncada em 2 de 3" in result

    async def test_list_attendance_sessions_parses_status_aliases_and_days(self) -> None:
        executor, mocks = _build_executor()
        tenant_id = uuid4()
        class_id = uuid4()
        session_id = uuid4()
        ctx = ToolExecutionContext(
            tenant_id=tenant_id, user_id=uuid4(), user_role=UserRole.COORDENADOR
        )

        mocks["list_tenant_sessions"].execute.return_value = Page(
            items=[
                AttendanceSession(
                    id=session_id,
                    subject_class_id=class_id,
                    day_code="ABC123",
                    expires_at=datetime.now(UTC),
                    status=SessionStatus.OPEN,
                    subject_class=SubjectClassInfo(class_id, "Cálculo I", "Matemática"),
                    room=RoomInfo(uuid4(), "Lab 01"),
                    total_students=30,
                    confirmed_count=22,
                    irregular_count=2,
                )
            ],
            total=1,
            page=1,
            page_size=15,
        )

        result = await executor.execute(
            ctx=ctx,
            tool_name=LIST_ATTENDANCE_SESSIONS_TOOL_NAME,
            arguments={"status": "open", "days": 7},
        )

        assert "Cálculo I" in result
        assert "Irregulares: 2" in result
        call_input = mocks["list_tenant_sessions"].execute.call_args.args[0]
        assert call_input.status == SessionStatus.OPEN
        assert call_input.opened_after is not None

    async def test_session_audit_summary_computes_exact_counts_and_filters_by_status(
        self,
    ) -> None:
        executor, mocks = _build_executor()
        tenant_id = uuid4()
        class_id = uuid4()
        session_id = uuid4()
        ctx = ToolExecutionContext(
            tenant_id=tenant_id, user_id=uuid4(), user_role=UserRole.COORDENADOR
        )

        mocks["subject_class_repo"].find_by_id_and_tenant.return_value = SubjectClass(
            id=class_id,
            tenant_id=tenant_id,
            professor_id=uuid4(),
            name="Cálculo I",
            discipline_name="Matemática",
        )
        mocks["get_session"].execute.return_value = AttendanceSession(
            id=session_id,
            subject_class_id=class_id,
            day_code="XYZ789",
            expires_at=datetime.now(UTC),
            status=SessionStatus.CLOSED,
        )
        mocks["list_session_roster"].execute.return_value = [
            SessionRosterItem(uuid4(), "Ana Presente", uuid4(), uuid4(), datetime.now(UTC), 5.0, True, RecordStatus.REGULAR),
            SessionRosterItem(uuid4(), "Bruno Aprovado", uuid4(), uuid4(), datetime.now(UTC), 60.0, False, RecordStatus.APPROVED),
            SessionRosterItem(uuid4(), "Carla Irregular", uuid4(), uuid4(), datetime.now(UTC), 120.5, False, RecordStatus.IRREGULAR),
            SessionRosterItem(uuid4(), "Diego Rejeitado", uuid4(), uuid4(), datetime.now(UTC), 300.0, False, RecordStatus.REJECTED),
            SessionRosterItem(uuid4(), "Eva Ausente", uuid4(), None, None, None, None, None),
        ]

        result = await executor.execute(
            ctx=ctx,
            tool_name=GET_SESSION_AUDIT_SUMMARY_TOOL_NAME,
            arguments={
                "subject_class_id": str(class_id),
                "session_id": str(session_id),
                "status_filter": "IRREGULAR",
            },
        )

        assert "PRESENTE: 2" in result
        assert "IRREGULAR (pendente de auditoria): 1" in result
        assert "REJEITADA: 1" in result
        assert "AUSENTE: 1" in result
        assert "Carla Irregular" in result
        assert "Ana Presente" not in result
        assert "Eva Ausente" not in result

    async def test_student_attendance_scopes_professor_and_enriches_with_class_report(
        self,
    ) -> None:
        executor, mocks = _build_executor()
        tenant_id = uuid4()
        class_id = uuid4()
        prof_member_id = uuid4()
        student_member_id = uuid4()
        ctx = ToolExecutionContext(
            tenant_id=tenant_id, user_id=uuid4(), user_role=UserRole.PROFESSOR
        )

        mocks["subject_class_repo"].find_by_id_and_tenant.return_value = SubjectClass(
            id=class_id,
            tenant_id=tenant_id,
            professor_id=prof_member_id,
            name="Algoritmos",
            discipline_name="Computação",
        )
        mocks["member_repo"].find_by_tenant_and_user.return_value = TenantMember(
            id=prof_member_id,
            tenant_id=tenant_id,
            user_id=ctx.user_id,
            role=UserRole.PROFESSOR,
        )
        mocks["list_students"].execute.return_value = Page(
            items=[
                TenantMember(
                    id=student_member_id,
                    tenant_id=tenant_id,
                    user_id=uuid4(),
                    role=UserRole.ALUNO,
                    name="João Silva",
                    attendance_rate=0.70,
                    turmas_count=2,
                    total_present=14,
                    total_absent=6,
                    total_sessions=20,
                    status="em_risco",
                )
            ],
            total=1,
            page=1,
            page_size=10,
        )
        mocks["get_student_report"].execute.return_value = StudentReport(
            tenant_member_id=student_member_id,
            student_name="João Silva",
            total_present=7,
            total_absent=3,
            total_irregular=1,
            frequency_rate=0.70,
            at_risk=True,
            avg_distance_meters=14.2,
            confirmations_near_limit=0,
        )

        result = await executor.execute(
            ctx=ctx,
            tool_name=GET_STUDENT_ATTENDANCE_TOOL_NAME,
            arguments={"search": "João", "subject_class_id": str(class_id)},
        )

        call_input = mocks["list_students"].execute.call_args.args[0]
        assert call_input.professor_user_id == ctx.user_id
        assert "João Silva" in result
        assert "irregulares: 1" in result
        assert "[EM RISCO]" in result

    async def test_list_rooms_formats_geofence_radius_and_metrics(self) -> None:
        executor, mocks = _build_executor()
        tenant_id = uuid4()
        ctx = ToolExecutionContext(
            tenant_id=tenant_id, user_id=uuid4(), user_role=UserRole.ADMIN
        )

        mocks["list_rooms"].execute.return_value = Page(
            items=[
                Room(
                    tenant_id=tenant_id,
                    name="Sala 102",
                    latitude=-23.5,
                    longitude=-46.6,
                    tolerance_radius_meters=35,
                )
            ],
            total=1,
            page=1,
            page_size=15,
        )
        mocks["get_room_metrics"].execute.return_value = RoomMetrics(
            total_rooms=5,
            avg_radius=45,
            precisas_count=3,
            amplas_count=2,
        )

        result = await executor.execute(
            ctx=ctx,
            tool_name=LIST_ROOMS_TOOL_NAME,
            arguments={"search": "102"},
        )

        assert "Sala 102" in result
        assert "35m" in result
        assert "total na instituição: 5" in result

    async def test_invalid_uuid_and_unknown_tool_return_graceful_pt_br_errors(self) -> None:
        executor, _ = _build_executor()
        ctx = ToolExecutionContext(tenant_id=uuid4(), user_id=uuid4(), user_role=UserRole.ADMIN)

        bad_uuid_result = await executor.execute(
            ctx=ctx,
            tool_name=GET_CLASS_ATTENDANCE_REPORT_TOOL_NAME,
            arguments={"subject_class_id": "not-a-uuid"},
        )
        assert "UUID válido" in bad_uuid_result

        unknown_result = await executor.execute(
            ctx=ctx,
            tool_name="delete_everything",
            arguments={},
        )
        assert "não suportada" in unknown_result
