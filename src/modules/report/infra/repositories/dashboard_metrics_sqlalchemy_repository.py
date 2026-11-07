from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from infra.database.models.attendance_record import AttendanceRecordModel
from infra.database.models.attendance_session import AttendanceSessionModel
from infra.database.models.enrollment import EnrollmentModel
from infra.database.models.subject_class import SubjectClassModel
from infra.database.models.tenant import TenantMemberModel
from infra.database.models.user import UserModel
from modules.report.domain.entities.dashboard_metrics import (
    AtRiskStudentMetric,
    DashboardMetrics,
    DayAttendanceMetric,
)
from modules.report.domain.services.student_calculator import RISK_THRESHOLD
from shared.enums.enrollment_status import EnrollmentStatus
from shared.enums.record_status import RecordStatus
from shared.enums.session_status import SessionStatus

DAY_LABELS = ("DOM", "SEG", "TER", "QUA", "QUI", "SEX", "SAB")
CRITICAL_RISK_THRESHOLD = 0.71


class DashboardMetricsSQLAlchemyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_metrics(
        self,
        tenant_id: UUID,
        professor_user_id: UUID | None = None,
        active: bool | None = None,
        now: datetime | None = None,
    ) -> DashboardMetrics:
        """Orquestra a busca das métricas consolidadas reutilizando o conjunto de turmas elegíveis."""
        class_ids = await self._get_eligible_class_ids(
            tenant_id=tenant_id,
            professor_user_id=professor_user_id,
            active=active,
        )

        current_time = now or datetime.now(timezone.utc)

        if not class_ids:
            return DashboardMetrics(
                total_classes=0,
                total_unique_students=0,
                average_attendance_rate=0.0,
                total_students_at_risk=0,
                week_frequency=self._empty_week_frequency(current_time),
                at_risk_students=[],
            )

        total_unique_students = await self._get_unique_students_count(class_ids)
        average_attendance_rate = await self._compute_30d_attendance_rate(class_ids)
        total_students_at_risk = await self._get_students_at_risk_count(class_ids)
        week_frequency = await self._compute_week_frequency(class_ids, now=current_time)
        at_risk_students = await self._get_top_at_risk_students(class_ids, limit=10)

        return DashboardMetrics(
            total_classes=len(class_ids),
            total_unique_students=total_unique_students,
            average_attendance_rate=average_attendance_rate,
            total_students_at_risk=total_students_at_risk,
            week_frequency=week_frequency,
            at_risk_students=at_risk_students,
        )

    async def _get_eligible_class_ids(
        self,
        tenant_id: UUID,
        professor_user_id: UUID | None,
        active: bool | None,
    ) -> list[UUID]:
        """Obtém os IDs das turmas válidas no tenant, aplicando filtros de papel e status ativo."""
        stmt = select(SubjectClassModel.id).where(
            SubjectClassModel.tenant_id == tenant_id,
            SubjectClassModel.deleted.is_(False),
        )
        if active is not None:
            stmt = stmt.where(SubjectClassModel.active.is_(active))

        if professor_user_id is not None:
            stmt = stmt.join(
                TenantMemberModel,
                TenantMemberModel.id == SubjectClassModel.professor_id,
            ).where(
                TenantMemberModel.user_id == professor_user_id,
                TenantMemberModel.deleted.is_(False),
            )

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def _get_unique_students_count(self, class_ids: list[UUID]) -> int:
        """Conta a quantidade de alunos únicos com matrícula ativa nas turmas elegíveis."""
        stmt = select(func.count(func.distinct(EnrollmentModel.tenant_member_id))).where(
            EnrollmentModel.subject_class_id.in_(class_ids),
            EnrollmentModel.deleted.is_(False),
            EnrollmentModel.status == EnrollmentStatus.ACTIVE,
        )
        result = await self.session.execute(stmt)
        return int(result.scalar_one() or 0)

    async def _compute_30d_attendance_rate(self, class_ids: list[UUID]) -> float:
        """Calcula a taxa de frequência média ponderada das turmas nos últimos 30 dias."""
        now = datetime.now(timezone.utc)
        thirty_days_ago = now - timedelta(days=30)

        # 1. Total de alunos ativos matriculados por turma
        enrollment_subquery = (
            select(
                EnrollmentModel.subject_class_id.label("subject_class_id"),
                func.count(EnrollmentModel.id).label("student_count"),
            )
            .where(
                EnrollmentModel.subject_class_id.in_(class_ids),
                EnrollmentModel.deleted.is_(False),
                EnrollmentModel.status == EnrollmentStatus.ACTIVE,
            )
            .group_by(EnrollmentModel.subject_class_id)
            .subquery()
        )

        # 2. Total de sessões realizadas nos últimos 30 dias (não canceladas)
        session_subquery = (
            select(
                AttendanceSessionModel.subject_class_id.label("subject_class_id"),
                func.count(AttendanceSessionModel.id).label("session_count"),
            )
            .where(
                AttendanceSessionModel.subject_class_id.in_(class_ids),
                AttendanceSessionModel.status != SessionStatus.CANCELLED,
                AttendanceSessionModel.opened_at >= thirty_days_ago,
            )
            .group_by(AttendanceSessionModel.subject_class_id)
            .subquery()
        )

        # 3. Total de presenças válidas (REGULAR ou APPROVED) de alunos ativos
        present_subquery = (
            select(
                AttendanceSessionModel.subject_class_id.label("subject_class_id"),
                func.count(AttendanceRecordModel.id).label("present_count"),
            )
            .join(
                AttendanceRecordModel,
                AttendanceRecordModel.session_id == AttendanceSessionModel.id,
            )
            .join(
                EnrollmentModel,
                and_(
                    EnrollmentModel.subject_class_id == AttendanceSessionModel.subject_class_id,
                    EnrollmentModel.tenant_member_id == AttendanceRecordModel.tenant_member_id,
                    EnrollmentModel.deleted.is_(False),
                    EnrollmentModel.status == EnrollmentStatus.ACTIVE,
                ),
            )
            .where(
                AttendanceSessionModel.subject_class_id.in_(class_ids),
                AttendanceSessionModel.status != SessionStatus.CANCELLED,
                AttendanceSessionModel.opened_at >= thirty_days_ago,
                AttendanceRecordModel.record_status.in_(
                    (RecordStatus.REGULAR, RecordStatus.APPROVED)
                ),
            )
            .group_by(AttendanceSessionModel.subject_class_id)
            .subquery()
        )

        # 4. Agrega por turma para calcular a razão esperados vs presentes
        stmt_rates = (
            select(
                SubjectClassModel.id,
                func.coalesce(enrollment_subquery.c.student_count, 0).label("student_count"),
                func.coalesce(session_subquery.c.session_count, 0).label("session_count"),
                func.coalesce(present_subquery.c.present_count, 0).label("present_count"),
            )
            .outerjoin(
                enrollment_subquery,
                enrollment_subquery.c.subject_class_id == SubjectClassModel.id,
            )
            .outerjoin(
                session_subquery,
                session_subquery.c.subject_class_id == SubjectClassModel.id,
            )
            .outerjoin(
                present_subquery,
                present_subquery.c.subject_class_id == SubjectClassModel.id,
            )
            .where(SubjectClassModel.id.in_(class_ids))
        )

        res_rates = await self.session.execute(stmt_rates)
        rows = res_rates.all()

        total_expected = sum(int(r.student_count) * int(r.session_count) for r in rows)
        total_presents = sum(int(r.present_count) for r in rows)

        if total_expected <= 0:
            return 0.0

        return round(total_presents / total_expected, 4)

    async def _get_students_at_risk_count(self, class_ids: list[UUID]) -> int:
        """Conta a quantidade de matrículas ativas em risco de reprovação por falta (< 75% de frequência)."""
        # 1. Total de sessões realizadas por turma (não canceladas)
        session_subquery = (
            select(
                AttendanceSessionModel.subject_class_id.label("subject_class_id"),
                func.count(AttendanceSessionModel.id).label("total_sessions"),
            )
            .where(
                AttendanceSessionModel.subject_class_id.in_(class_ids),
                AttendanceSessionModel.status != SessionStatus.CANCELLED,
            )
            .group_by(AttendanceSessionModel.subject_class_id)
            .subquery()
        )

        # 2. Total de presenças válidas de cada aluno em cada turma
        presence_subquery = (
            select(
                AttendanceSessionModel.subject_class_id.label("subject_class_id"),
                AttendanceRecordModel.tenant_member_id.label("tenant_member_id"),
                func.count(AttendanceRecordModel.id).label("total_presences"),
            )
            .join(
                AttendanceSessionModel,
                AttendanceSessionModel.id == AttendanceRecordModel.session_id,
            )
            .where(
                AttendanceSessionModel.subject_class_id.in_(class_ids),
                AttendanceSessionModel.status != SessionStatus.CANCELLED,
                AttendanceRecordModel.record_status.in_(
                    (RecordStatus.REGULAR, RecordStatus.APPROVED)
                ),
            )
            .group_by(
                AttendanceSessionModel.subject_class_id,
                AttendanceRecordModel.tenant_member_id,
            )
            .subquery()
        )

        # 3. Cruzamento com matrículas ativas das turmas elegíveis
        stmt = (
            select(func.count(EnrollmentModel.id))
            .join(
                session_subquery,
                session_subquery.c.subject_class_id == EnrollmentModel.subject_class_id,
            )
            .outerjoin(
                presence_subquery,
                and_(
                    presence_subquery.c.subject_class_id == EnrollmentModel.subject_class_id,
                    presence_subquery.c.tenant_member_id == EnrollmentModel.tenant_member_id,
                ),
            )
            .where(
                EnrollmentModel.subject_class_id.in_(class_ids),
                EnrollmentModel.deleted.is_(False),
                EnrollmentModel.status == EnrollmentStatus.ACTIVE,
                session_subquery.c.total_sessions > 0,
                (func.coalesce(presence_subquery.c.total_presences, 0) * 1.0)
                < (session_subquery.c.total_sessions * RISK_THRESHOLD),
            )
        )

        result = await self.session.execute(stmt)
        return int(result.scalar_one() or 0)

    def _empty_week_frequency(self, now: datetime | None = None) -> list[DayAttendanceMetric]:
        """Gera os 7 dias da semana atual (DOM a SAB) zerados quando não há turmas ou sessões."""
        current = now or datetime.now(timezone.utc)
        today = current.date()
        days_since_sunday = (today.weekday() + 1) % 7
        sunday = today - timedelta(days=days_since_sunday)

        return [
            DayAttendanceMetric(
                date=(sunday + timedelta(days=i)).isoformat(),
                day_of_week=i,
                day_label=DAY_LABELS[i],
                attendance_rate=0.0,
                total_sessions=0,
                total_expected=0,
                total_presents=0,
            )
            for i in range(7)
        ]

    async def _compute_week_frequency(
        self, class_ids: list[UUID], now: datetime | None = None
    ) -> list[DayAttendanceMetric]:
        """Calcula a frequência diária agregada de Domingo a Sábado da semana atual."""
        current = now or datetime.now(timezone.utc)
        today = current.date()
        days_since_sunday = (today.weekday() + 1) % 7
        sunday = today - timedelta(days=days_since_sunday)
        saturday = sunday + timedelta(days=6)

        start_of_week = datetime(
            sunday.year, sunday.month, sunday.day, 0, 0, 0, tzinfo=timezone.utc
        )
        end_of_week = datetime(
            saturday.year, saturday.month, saturday.day, 23, 59, 59, 999999, tzinfo=timezone.utc
        )

        # 1. Total de alunos ativos matriculados por turma
        stmt_enrollments = (
            select(
                EnrollmentModel.subject_class_id,
                func.count(EnrollmentModel.id).label("student_count"),
            )
            .where(
                EnrollmentModel.subject_class_id.in_(class_ids),
                EnrollmentModel.deleted.is_(False),
                EnrollmentModel.status == EnrollmentStatus.ACTIVE,
            )
            .group_by(EnrollmentModel.subject_class_id)
        )
        res_enrollments = await self.session.execute(stmt_enrollments)
        class_students: dict[UUID, int] = {
            row.subject_class_id: int(row.student_count) for row in res_enrollments.all()
        }

        # 2. Subquery de presenças válidas de alunos ativos por sessão na semana
        present_subquery = (
            select(
                AttendanceRecordModel.session_id.label("session_id"),
                func.count(AttendanceRecordModel.id).label("present_count"),
            )
            .join(
                AttendanceSessionModel,
                AttendanceSessionModel.id == AttendanceRecordModel.session_id,
            )
            .join(
                EnrollmentModel,
                and_(
                    EnrollmentModel.subject_class_id == AttendanceSessionModel.subject_class_id,
                    EnrollmentModel.tenant_member_id == AttendanceRecordModel.tenant_member_id,
                    EnrollmentModel.deleted.is_(False),
                    EnrollmentModel.status == EnrollmentStatus.ACTIVE,
                ),
            )
            .where(
                AttendanceSessionModel.subject_class_id.in_(class_ids),
                AttendanceSessionModel.status != SessionStatus.CANCELLED,
                AttendanceSessionModel.opened_at >= start_of_week,
                AttendanceSessionModel.opened_at <= end_of_week,
                AttendanceRecordModel.record_status.in_(
                    (RecordStatus.REGULAR, RecordStatus.APPROVED)
                ),
            )
            .group_by(AttendanceRecordModel.session_id)
            .subquery()
        )

        # 3. Busca as sessões realizadas na semana
        stmt_sessions = (
            select(
                AttendanceSessionModel.id,
                AttendanceSessionModel.subject_class_id,
                AttendanceSessionModel.opened_at,
                func.coalesce(present_subquery.c.present_count, 0).label("present_count"),
            )
            .outerjoin(
                present_subquery,
                present_subquery.c.session_id == AttendanceSessionModel.id,
            )
            .where(
                AttendanceSessionModel.subject_class_id.in_(class_ids),
                AttendanceSessionModel.status != SessionStatus.CANCELLED,
                AttendanceSessionModel.opened_at >= start_of_week,
                AttendanceSessionModel.opened_at <= end_of_week,
            )
        )
        res_sessions = await self.session.execute(stmt_sessions)
        session_rows = res_sessions.all()

        # 4. Agrega nos 7 dias de Domingo a Sábado
        days_dict = {
            (sunday + timedelta(days=i)).isoformat(): {
                "day_of_week": i,
                "day_label": DAY_LABELS[i],
                "date": (sunday + timedelta(days=i)).isoformat(),
                "total_sessions": 0,
                "total_expected": 0,
                "total_presents": 0,
            }
            for i in range(7)
        }

        for row in session_rows:
            sess_date_str = row.opened_at.date().isoformat()
            if sess_date_str in days_dict:
                expected = class_students.get(row.subject_class_id, 0)
                days_dict[sess_date_str]["total_sessions"] += 1
                days_dict[sess_date_str]["total_expected"] += expected
                days_dict[sess_date_str]["total_presents"] += int(row.present_count)

        return [
            DayAttendanceMetric(
                date=d["date"],
                day_of_week=d["day_of_week"],
                day_label=d["day_label"],
                attendance_rate=(
                    round(d["total_presents"] / d["total_expected"], 4)
                    if d["total_expected"] > 0
                    else 0.0
                ),
                total_sessions=d["total_sessions"],
                total_expected=d["total_expected"],
                total_presents=d["total_presents"],
            )
            for d in days_dict.values()
        ]

    async def _get_top_at_risk_students(
        self, class_ids: list[UUID], limit: int = 10
    ) -> list[AtRiskStudentMetric]:
        """Retorna as top matrículas em situação mais crítica de falta (< 75%), ordenadas pela menor frequência."""
        # 1. Total de sessões realizadas por turma (não canceladas)
        session_subquery = (
            select(
                AttendanceSessionModel.subject_class_id.label("subject_class_id"),
                func.count(AttendanceSessionModel.id).label("total_sessions"),
            )
            .where(
                AttendanceSessionModel.subject_class_id.in_(class_ids),
                AttendanceSessionModel.status != SessionStatus.CANCELLED,
            )
            .group_by(AttendanceSessionModel.subject_class_id)
            .subquery()
        )

        # 2. Total de presenças válidas de cada aluno em cada turma
        presence_subquery = (
            select(
                AttendanceSessionModel.subject_class_id.label("subject_class_id"),
                AttendanceRecordModel.tenant_member_id.label("tenant_member_id"),
                func.count(AttendanceRecordModel.id).label("total_presences"),
            )
            .join(
                AttendanceSessionModel,
                AttendanceSessionModel.id == AttendanceRecordModel.session_id,
            )
            .where(
                AttendanceSessionModel.subject_class_id.in_(class_ids),
                AttendanceSessionModel.status != SessionStatus.CANCELLED,
                AttendanceRecordModel.record_status.in_(
                    (RecordStatus.REGULAR, RecordStatus.APPROVED)
                ),
            )
            .group_by(
                AttendanceSessionModel.subject_class_id,
                AttendanceRecordModel.tenant_member_id,
            )
            .subquery()
        )

        # 3. Expressões SQL para presenças, faltas e taxa
        presences_col = func.coalesce(presence_subquery.c.total_presences, 0)
        sessions_col = session_subquery.c.total_sessions
        rate_expr = presences_col * 1.0 / sessions_col
        absences_expr = sessions_col - presences_col

        stmt = (
            select(
                EnrollmentModel.id.label("enrollment_id"),
                UserModel.name.label("student_name"),
                SubjectClassModel.name.label("class_name"),
                sessions_col.label("total_sessions"),
                absences_expr.label("absences"),
                rate_expr.label("attendance_rate"),
            )
            .join(
                SubjectClassModel,
                SubjectClassModel.id == EnrollmentModel.subject_class_id,
            )
            .join(
                TenantMemberModel,
                TenantMemberModel.id == EnrollmentModel.tenant_member_id,
            )
            .join(
                UserModel,
                UserModel.id == TenantMemberModel.user_id,
            )
            .join(
                session_subquery,
                session_subquery.c.subject_class_id == EnrollmentModel.subject_class_id,
            )
            .outerjoin(
                presence_subquery,
                and_(
                    presence_subquery.c.subject_class_id == EnrollmentModel.subject_class_id,
                    presence_subquery.c.tenant_member_id == EnrollmentModel.tenant_member_id,
                ),
            )
            .where(
                EnrollmentModel.subject_class_id.in_(class_ids),
                EnrollmentModel.deleted.is_(False),
                EnrollmentModel.status == EnrollmentStatus.ACTIVE,
                sessions_col > 0,
                presences_col * 1.0 < sessions_col * RISK_THRESHOLD,
            )
            .order_by(
                rate_expr.asc(),
                absences_expr.desc(),
                UserModel.name.asc(),
            )
            .limit(limit)
        )

        result = await self.session.execute(stmt)
        rows = result.all()

        return [
            AtRiskStudentMetric(
                enrollment_id=row.enrollment_id,
                student_name=row.student_name,
                class_name=row.class_name,
                total_sessions=int(row.total_sessions),
                absences=int(row.absences),
                attendance_rate=round(float(row.attendance_rate), 4),
                critical=bool(float(row.attendance_rate) <= CRITICAL_RISK_THRESHOLD),
            )
            for row in rows
        ]
