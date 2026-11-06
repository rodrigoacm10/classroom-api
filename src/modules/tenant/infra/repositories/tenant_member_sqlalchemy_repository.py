from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from infra.database.models.attendance_record import AttendanceRecordModel
from infra.database.models.attendance_session import AttendanceSessionModel
from infra.database.models.enrollment import EnrollmentModel
from infra.database.models.subject_class import SubjectClassModel
from infra.database.models.tenant import TenantMemberModel
from infra.database.models.user import UserModel
from modules.tenant.domain.entities.students_metrics import StudentsMetrics
from modules.tenant.domain.entities.tenant_member import TenantMember
from modules.tenant.infra.mappers.tenant_member_mapper import TenantMemberMapper
from shared.enums.enrollment_status import EnrollmentStatus
from shared.enums.record_status import RecordStatus
from shared.enums.session_status import SessionStatus
from shared.enums.user_role import UserRole
from shared.pagination import Page, PaginationParams


class TenantMemberSQLAlchemyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def find_by_id(
        self, member_id: UUID, include_deleted: bool = False
    ) -> TenantMember | None:
        conditions = [TenantMemberModel.id == member_id]
        if not include_deleted:
            conditions.append(TenantMemberModel.deleted.is_(False))

        stmt = (
            select(TenantMemberModel, UserModel.name, UserModel.email)
            .join(UserModel, UserModel.id == TenantMemberModel.user_id)
            .where(*conditions)
        )
        result = await self.session.execute(stmt)
        row = result.first()
        if not row:
            return None
        model, user_name, user_email = row
        return TenantMemberMapper.to_domain(model, user_name, user_email)

    async def find_by_tenant_and_user(
        self,
        tenant_id: UUID,
        user_id: UUID,
        include_deleted: bool = False,
    ) -> TenantMember | None:
        conditions = [
            TenantMemberModel.tenant_id == tenant_id,
            TenantMemberModel.user_id == user_id,
        ]
        if not include_deleted:
            conditions.append(TenantMemberModel.deleted.is_(False))

        stmt = (
            select(TenantMemberModel, UserModel.name, UserModel.email)
            .join(UserModel, UserModel.id == TenantMemberModel.user_id)
            .where(*conditions)
        )
        result = await self.session.execute(stmt)
        row = result.first()
        if not row:
            return None
        model, user_name, user_email = row
        return TenantMemberMapper.to_domain(model, user_name, user_email)

    async def find_by_user_id(
        self, user_id: UUID, include_deleted: bool = False
    ) -> list[TenantMember]:
        conditions = [TenantMemberModel.user_id == user_id]
        if not include_deleted:
            conditions.append(TenantMemberModel.deleted.is_(False))

        stmt = (
            select(TenantMemberModel, UserModel.name, UserModel.email)
            .join(UserModel, UserModel.id == TenantMemberModel.user_id)
            .where(*conditions)
        )
        result = await self.session.execute(stmt)
        rows = result.all()
        return [TenantMemberMapper.to_domain(m, name, email) for m, name, email in rows]

    async def find_by_tenant_id_paginated(
        self,
        tenant_id: UUID,
        pagination: PaginationParams,
        role: UserRole | None = None,
        exclude_role: UserRole | None = None,
        search: str | None = None,
        subject_class_id: UUID | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
        include_deleted: bool = False,
    ) -> Page[TenantMember]:
        conditions = [TenantMemberModel.tenant_id == tenant_id]
        if role is not None:
            conditions.append(TenantMemberModel.role == role)
        if exclude_role is not None:
            conditions.append(TenantMemberModel.role != exclude_role)
        if created_after is not None:
            conditions.append(TenantMemberModel.created_at >= created_after)
        if created_before is not None:
            conditions.append(TenantMemberModel.created_at <= created_before)
        if not include_deleted:
            conditions.append(TenantMemberModel.deleted.is_(False))

        # Query de contagem total
        count_stmt = select(func.count(func.distinct(TenantMemberModel.id))).where(*conditions)
        if search:
            count_stmt = count_stmt.join(
                UserModel, UserModel.id == TenantMemberModel.user_id
            ).where(
                or_(
                    UserModel.name.ilike(f"%{search}%"),
                    UserModel.email.ilike(f"%{search}%"),
                )
            )
        if subject_class_id:
            count_stmt = count_stmt.join(
                EnrollmentModel,
                and_(
                    EnrollmentModel.tenant_member_id == TenantMemberModel.id,
                    EnrollmentModel.deleted.is_(False),
                ),
            ).where(EnrollmentModel.subject_class_id == subject_class_id)

        total = int((await self.session.execute(count_stmt)).scalar_one() or 0)

        # Query dos itens paginados com UserModel.name e UserModel.email
        items_stmt = (
            select(TenantMemberModel, UserModel.name, UserModel.email)
            .join(UserModel, UserModel.id == TenantMemberModel.user_id)
            .where(*conditions)
        )
        if search:
            items_stmt = items_stmt.where(
                or_(
                    UserModel.name.ilike(f"%{search}%"),
                    UserModel.email.ilike(f"%{search}%"),
                )
            )
        if subject_class_id:
            items_stmt = items_stmt.join(
                EnrollmentModel,
                and_(
                    EnrollmentModel.tenant_member_id == TenantMemberModel.id,
                    EnrollmentModel.deleted.is_(False),
                ),
            ).where(EnrollmentModel.subject_class_id == subject_class_id)

        items_stmt = (
            items_stmt.order_by(TenantMemberModel.created_at.desc())
            .offset(pagination.offset)
            .limit(pagination.page_size)
        )

        result = await self.session.execute(items_stmt)
        rows = result.all()
        items = [
            TenantMemberMapper.to_domain(m, user_name, user_email)
            for m, user_name, user_email in rows
        ]

        return Page.from_params(items, total=total, pagination=pagination)

    async def find_students_with_metrics_paginated(
        self,
        tenant_id: UUID,
        pagination: PaginationParams,
        search: str | None = None,
        subject_class_id: UUID | None = None,
        professor_user_id: UUID | None = None,
        status: str | None = None,
        sort_by: str = "name",
        order: str = "asc",
        include_deleted: bool = False,
    ) -> Page[TenantMember]:
        # 1. Base query for eligible student classes in the tenant
        eligible_classes = select(SubjectClassModel.id.label("class_id")).where(
            SubjectClassModel.tenant_id == tenant_id,
            SubjectClassModel.deleted.is_(False),
        )
        if professor_user_id is not None:
            ProfMember = aliased(TenantMemberModel, name="prof_member_classes")
            eligible_classes = eligible_classes.join(
                ProfMember, ProfMember.id == SubjectClassModel.professor_id
            ).where(
                ProfMember.user_id == professor_user_id,
                ProfMember.deleted.is_(False),
            )
        if subject_class_id is not None:
            eligible_classes = eligible_classes.where(SubjectClassModel.id == subject_class_id)

        eligible_classes_sub = eligible_classes.subquery()

        # Student active enrollments in eligible classes
        student_classes = (
            select(
                EnrollmentModel.tenant_member_id.label("tenant_member_id"),
                EnrollmentModel.subject_class_id.label("subject_class_id"),
            )
            .join(
                eligible_classes_sub,
                eligible_classes_sub.c.class_id == EnrollmentModel.subject_class_id,
            )
            .where(
                EnrollmentModel.deleted.is_(False),
                EnrollmentModel.status == EnrollmentStatus.ACTIVE,
            )
            .subquery()
        )

        # Turmas count per student
        turmas_count_sub = (
            select(
                student_classes.c.tenant_member_id.label("tenant_member_id"),
                func.count(student_classes.c.subject_class_id).label("turmas_count"),
            )
            .group_by(student_classes.c.tenant_member_id)
            .subquery()
        )

        # Total sessions per student in eligible classes
        sessions_sub = (
            select(
                student_classes.c.tenant_member_id.label("tenant_member_id"),
                func.count(AttendanceSessionModel.id).label("total_sessions"),
            )
            .join(
                AttendanceSessionModel,
                AttendanceSessionModel.subject_class_id == student_classes.c.subject_class_id,
            )
            .where(
                AttendanceSessionModel.status != SessionStatus.CANCELLED,
            )
            .group_by(student_classes.c.tenant_member_id)
            .subquery()
        )

        # Total presents per student in eligible classes
        presents_sub = (
            select(
                student_classes.c.tenant_member_id.label("tenant_member_id"),
                func.count(AttendanceRecordModel.id).label("total_present"),
            )
            .join(
                AttendanceSessionModel,
                AttendanceSessionModel.subject_class_id == student_classes.c.subject_class_id,
            )
            .join(
                AttendanceRecordModel,
                and_(
                    AttendanceRecordModel.session_id == AttendanceSessionModel.id,
                    AttendanceRecordModel.tenant_member_id == student_classes.c.tenant_member_id,
                ),
            )
            .where(
                AttendanceSessionModel.status != SessionStatus.CANCELLED,
                AttendanceRecordModel.record_status.in_(
                    (RecordStatus.REGULAR, RecordStatus.APPROVED)
                ),
            )
            .group_by(student_classes.c.tenant_member_id)
            .subquery()
        )

        # Conditions on student
        conditions = [
            TenantMemberModel.tenant_id == tenant_id,
            TenantMemberModel.role == UserRole.ALUNO,
        ]
        if not include_deleted:
            conditions.append(TenantMemberModel.deleted.is_(False))

        count_stmt = (
            select(func.count(func.distinct(TenantMemberModel.id)))
            .join(UserModel, UserModel.id == TenantMemberModel.user_id)
            .where(*conditions)
        )
        if search:
            count_stmt = count_stmt.where(
                or_(
                    UserModel.name.ilike(f"%{search}%"),
                    UserModel.email.ilike(f"%{search}%"),
                )
            )
        if subject_class_id:
            count_stmt = count_stmt.join(
                EnrollmentModel,
                and_(
                    EnrollmentModel.tenant_member_id == TenantMemberModel.id,
                    EnrollmentModel.deleted.is_(False),
                    EnrollmentModel.status == EnrollmentStatus.ACTIVE,
                ),
            ).where(EnrollmentModel.subject_class_id == subject_class_id)
        if status == "regular":
            count_stmt = count_stmt.join(
                student_classes,
                student_classes.c.tenant_member_id == TenantMemberModel.id,
            )
        elif status == "sem_turma":
            count_stmt = count_stmt.where(
                ~select(1)
                .where(student_classes.c.tenant_member_id == TenantMemberModel.id)
                .exists()
            )

        total = int((await self.session.execute(count_stmt)).scalar_one() or 0)

        items_stmt = (
            select(
                TenantMemberModel,
                UserModel.name,
                UserModel.email,
                func.coalesce(turmas_count_sub.c.turmas_count, 0).label("turmas_count"),
                func.coalesce(sessions_sub.c.total_sessions, 0).label("total_sessions"),
                func.coalesce(presents_sub.c.total_present, 0).label("total_present"),
            )
            .join(UserModel, UserModel.id == TenantMemberModel.user_id)
            .outerjoin(
                turmas_count_sub,
                turmas_count_sub.c.tenant_member_id == TenantMemberModel.id,
            )
            .outerjoin(
                sessions_sub,
                sessions_sub.c.tenant_member_id == TenantMemberModel.id,
            )
            .outerjoin(
                presents_sub,
                presents_sub.c.tenant_member_id == TenantMemberModel.id,
            )
            .where(*conditions)
        )

        if search:
            items_stmt = items_stmt.where(
                or_(
                    UserModel.name.ilike(f"%{search}%"),
                    UserModel.email.ilike(f"%{search}%"),
                )
            )
        if subject_class_id:
            items_stmt = items_stmt.where(turmas_count_sub.c.turmas_count > 0)
        if status == "regular":
            items_stmt = items_stmt.where(func.coalesce(turmas_count_sub.c.turmas_count, 0) > 0)
        elif status == "sem_turma":
            items_stmt = items_stmt.where(func.coalesce(turmas_count_sub.c.turmas_count, 0) == 0)

        order_clauses: list[Any] = []
        is_asc = order.lower() == "asc"
        if sort_by == "name":
            order_clauses.append(UserModel.name.asc() if is_asc else UserModel.name.desc())
        elif sort_by == "turmas_count":
            order_clauses.append(
                func.coalesce(turmas_count_sub.c.turmas_count, 0).asc()
                if is_asc
                else func.coalesce(turmas_count_sub.c.turmas_count, 0).desc()
            )
        elif sort_by == "created_at":
            order_clauses.append(
                TenantMemberModel.created_at.asc()
                if is_asc
                else TenantMemberModel.created_at.desc()
            )
        else:
            order_clauses.append(UserModel.name.asc() if is_asc else UserModel.name.desc())

        order_clauses.append(TenantMemberModel.id.asc())

        items_stmt = (
            items_stmt.order_by(*order_clauses)
            .offset(pagination.offset)
            .limit(pagination.page_size)
        )

        result = await self.session.execute(items_stmt)
        rows = result.all()

        items: list[TenantMember] = []
        for m, user_name, user_email, t_count, sessions, presents in rows:
            turmas_count = int(t_count)
            total_sessions = int(sessions)
            total_present = int(presents)
            total_absent = max(total_sessions - total_present, 0)
            if turmas_count == 0:
                attendance_rate = 0.0
                status_str = "sem_turma"
            elif total_sessions == 0:
                attendance_rate = 1.0
                status_str = "regular"
            else:
                attendance_rate = round(total_present / total_sessions, 4)
                status_str = "at_risk" if attendance_rate < 0.75 else "regular"

            items.append(
                TenantMemberMapper.to_domain(
                    model=m,
                    user_name=user_name,
                    user_email=user_email,
                    turmas_count=turmas_count,
                    attendance_rate=attendance_rate,
                    total_sessions=total_sessions,
                    total_present=total_present,
                    total_absent=total_absent,
                    status=status_str,
                )
            )

        return Page.from_params(items, total=total, pagination=pagination)

    async def find_student_with_metrics_by_id(
        self,
        tenant_id: UUID,
        student_id: UUID,
        professor_user_id: UUID | None = None,
        include_deleted: bool = False,
    ) -> TenantMember | None:
        eligible_classes = select(SubjectClassModel.id.label("class_id")).where(
            SubjectClassModel.tenant_id == tenant_id,
            SubjectClassModel.deleted.is_(False),
        )
        if professor_user_id is not None:
            ProfMember = aliased(TenantMemberModel, name="prof_member_single")
            eligible_classes = eligible_classes.join(
                ProfMember, ProfMember.id == SubjectClassModel.professor_id
            ).where(
                ProfMember.user_id == professor_user_id,
                ProfMember.deleted.is_(False),
            )

        eligible_classes_sub = eligible_classes.subquery()

        student_classes = (
            select(
                EnrollmentModel.tenant_member_id.label("tenant_member_id"),
                EnrollmentModel.subject_class_id.label("subject_class_id"),
            )
            .join(
                eligible_classes_sub,
                eligible_classes_sub.c.class_id == EnrollmentModel.subject_class_id,
            )
            .where(
                EnrollmentModel.deleted.is_(False),
                EnrollmentModel.status == EnrollmentStatus.ACTIVE,
                EnrollmentModel.tenant_member_id == student_id,
            )
            .subquery()
        )

        turmas_count_sub = (
            select(
                student_classes.c.tenant_member_id.label("tenant_member_id"),
                func.count(student_classes.c.subject_class_id).label("turmas_count"),
            )
            .group_by(student_classes.c.tenant_member_id)
            .subquery()
        )

        sessions_sub = (
            select(
                student_classes.c.tenant_member_id.label("tenant_member_id"),
                func.count(AttendanceSessionModel.id).label("total_sessions"),
            )
            .join(
                AttendanceSessionModel,
                AttendanceSessionModel.subject_class_id == student_classes.c.subject_class_id,
            )
            .where(
                AttendanceSessionModel.status != SessionStatus.CANCELLED,
            )
            .group_by(student_classes.c.tenant_member_id)
            .subquery()
        )

        presents_sub = (
            select(
                student_classes.c.tenant_member_id.label("tenant_member_id"),
                func.count(AttendanceRecordModel.id).label("total_present"),
            )
            .join(
                AttendanceSessionModel,
                AttendanceSessionModel.subject_class_id == student_classes.c.subject_class_id,
            )
            .join(
                AttendanceRecordModel,
                and_(
                    AttendanceRecordModel.session_id == AttendanceSessionModel.id,
                    AttendanceRecordModel.tenant_member_id == student_classes.c.tenant_member_id,
                ),
            )
            .where(
                AttendanceSessionModel.status != SessionStatus.CANCELLED,
                AttendanceRecordModel.record_status.in_(
                    (RecordStatus.REGULAR, RecordStatus.APPROVED)
                ),
            )
            .group_by(student_classes.c.tenant_member_id)
            .subquery()
        )

        conditions = [
            TenantMemberModel.id == student_id,
            TenantMemberModel.tenant_id == tenant_id,
            TenantMemberModel.role == UserRole.ALUNO,
        ]
        if not include_deleted:
            conditions.append(TenantMemberModel.deleted.is_(False))

        stmt = (
            select(
                TenantMemberModel,
                UserModel.name,
                UserModel.email,
                func.coalesce(turmas_count_sub.c.turmas_count, 0).label("turmas_count"),
                func.coalesce(sessions_sub.c.total_sessions, 0).label("total_sessions"),
                func.coalesce(presents_sub.c.total_present, 0).label("total_present"),
            )
            .join(UserModel, UserModel.id == TenantMemberModel.user_id)
            .outerjoin(
                turmas_count_sub,
                turmas_count_sub.c.tenant_member_id == TenantMemberModel.id,
            )
            .outerjoin(
                sessions_sub,
                sessions_sub.c.tenant_member_id == TenantMemberModel.id,
            )
            .outerjoin(
                presents_sub,
                presents_sub.c.tenant_member_id == TenantMemberModel.id,
            )
            .where(*conditions)
        )

        result = await self.session.execute(stmt)
        row = result.first()
        if not row:
            return None

        m, user_name, user_email, t_count, sessions, presents = row
        turmas_count = int(t_count)
        total_sessions = int(sessions)
        total_present = int(presents)
        total_absent = max(total_sessions - total_present, 0)
        if turmas_count == 0:
            attendance_rate = 0.0
            status_str = "sem_turma"
        elif total_sessions == 0:
            attendance_rate = 1.0
            status_str = "regular"
        else:
            attendance_rate = round(total_present / total_sessions, 2)
            status_str = "at_risk" if attendance_rate < 0.75 else "regular"

        return TenantMemberMapper.to_domain(
            model=m,
            user_name=user_name,
            user_email=user_email,
            turmas_count=turmas_count,
            attendance_rate=attendance_rate,
            total_sessions=total_sessions,
            total_present=total_present,
            total_absent=total_absent,
            status=status_str,
        )

    async def get_students_metrics(
        self,
        tenant_id: UUID,
        professor_user_id: UUID | None = None,
    ) -> StudentsMetrics:
        eligible_classes = select(SubjectClassModel.id.label("class_id")).where(
            SubjectClassModel.tenant_id == tenant_id,
            SubjectClassModel.deleted.is_(False),
        )
        if professor_user_id is not None:
            ProfMember = aliased(TenantMemberModel, name="prof_member_kpi")
            eligible_classes = eligible_classes.join(
                ProfMember, ProfMember.id == SubjectClassModel.professor_id
            ).where(
                ProfMember.user_id == professor_user_id,
                ProfMember.deleted.is_(False),
            )

        eligible_classes_sub = eligible_classes.subquery()

        # 1. Total students
        if professor_user_id is not None:
            tot_students_stmt = (
                select(func.count(func.distinct(EnrollmentModel.tenant_member_id)))
                .join(
                    eligible_classes_sub,
                    eligible_classes_sub.c.class_id == EnrollmentModel.subject_class_id,
                )
                .join(
                    TenantMemberModel,
                    TenantMemberModel.id == EnrollmentModel.tenant_member_id,
                )
                .where(
                    EnrollmentModel.deleted.is_(False),
                    EnrollmentModel.status == EnrollmentStatus.ACTIVE,
                    TenantMemberModel.deleted.is_(False),
                    TenantMemberModel.role == UserRole.ALUNO,
                )
            )
        else:
            tot_students_stmt = select(func.count(TenantMemberModel.id)).where(
                TenantMemberModel.tenant_id == tenant_id,
                TenantMemberModel.role == UserRole.ALUNO,
                TenantMemberModel.deleted.is_(False),
            )

        total_students = int((await self.session.execute(tot_students_stmt)).scalar_one() or 0)

        # 2. Total enrollments
        enroll_stmt = (
            select(func.count(EnrollmentModel.id))
            .join(
                eligible_classes_sub,
                eligible_classes_sub.c.class_id == EnrollmentModel.subject_class_id,
            )
            .join(
                TenantMemberModel,
                TenantMemberModel.id == EnrollmentModel.tenant_member_id,
            )
            .where(
                EnrollmentModel.deleted.is_(False),
                EnrollmentModel.status == EnrollmentStatus.ACTIVE,
                TenantMemberModel.deleted.is_(False),
                TenantMemberModel.role == UserRole.ALUNO,
            )
        )
        total_enrollments = int((await self.session.execute(enroll_stmt)).scalar_one() or 0)
        avg_classes = round(total_enrollments / total_students, 1) if total_students > 0 else 0.0

        # 3. Attendance per student across eligible classes
        student_classes = (
            select(
                EnrollmentModel.tenant_member_id.label("tenant_member_id"),
                EnrollmentModel.subject_class_id.label("subject_class_id"),
            )
            .join(
                eligible_classes_sub,
                eligible_classes_sub.c.class_id == EnrollmentModel.subject_class_id,
            )
            .join(
                TenantMemberModel,
                TenantMemberModel.id == EnrollmentModel.tenant_member_id,
            )
            .where(
                EnrollmentModel.deleted.is_(False),
                EnrollmentModel.status == EnrollmentStatus.ACTIVE,
                TenantMemberModel.deleted.is_(False),
                TenantMemberModel.role == UserRole.ALUNO,
            )
            .subquery()
        )

        sessions_sub = (
            select(
                student_classes.c.tenant_member_id.label("tenant_member_id"),
                func.count(AttendanceSessionModel.id).label("total_sessions"),
            )
            .join(
                AttendanceSessionModel,
                AttendanceSessionModel.subject_class_id == student_classes.c.subject_class_id,
            )
            .where(AttendanceSessionModel.status != SessionStatus.CANCELLED)
            .group_by(student_classes.c.tenant_member_id)
            .subquery()
        )

        presents_sub = (
            select(
                student_classes.c.tenant_member_id.label("tenant_member_id"),
                func.count(AttendanceRecordModel.id).label("total_present"),
            )
            .join(
                AttendanceSessionModel,
                AttendanceSessionModel.subject_class_id == student_classes.c.subject_class_id,
            )
            .join(
                AttendanceRecordModel,
                and_(
                    AttendanceRecordModel.session_id == AttendanceSessionModel.id,
                    AttendanceRecordModel.tenant_member_id == student_classes.c.tenant_member_id,
                ),
            )
            .where(
                AttendanceSessionModel.status != SessionStatus.CANCELLED,
                AttendanceRecordModel.record_status.in_(
                    (RecordStatus.REGULAR, RecordStatus.APPROVED)
                ),
            )
            .group_by(student_classes.c.tenant_member_id)
            .subquery()
        )

        student_att_stmt = (
            select(
                student_classes.c.tenant_member_id,
                func.coalesce(sessions_sub.c.total_sessions, 0).label("total_sessions"),
                func.coalesce(presents_sub.c.total_present, 0).label("total_present"),
            )
            .outerjoin(
                sessions_sub,
                sessions_sub.c.tenant_member_id == student_classes.c.tenant_member_id,
            )
            .outerjoin(
                presents_sub,
                presents_sub.c.tenant_member_id == student_classes.c.tenant_member_id,
            )
            .distinct()
        )

        att_rows = (await self.session.execute(student_att_stmt)).all()
        enrolled_ids = set()
        rates = []
        students_at_risk = 0

        for r in att_rows:
            enrolled_ids.add(r.tenant_member_id)
            sess = int(r.total_sessions)
            pres = int(r.total_present)
            if sess > 0:
                rate = pres / sess
                rates.append(rate)
                if rate < 0.75:
                    students_at_risk += 1

        students_no_class = max(total_students - len(enrolled_ids), 0)
        avg_rate = round(sum(rates) / len(rates), 4) if rates else 0.0

        return StudentsMetrics(
            total_students=total_students,
            avg_classes_per_student=avg_classes,
            total_enrollments=total_enrollments,
            average_attendance_rate=avg_rate,
            students_at_risk=students_at_risk,
            students_no_class=students_no_class,
        )

    async def count_active_admins(self, tenant_id: UUID) -> int:
        stmt = select(func.count(TenantMemberModel.id)).where(
            TenantMemberModel.tenant_id == tenant_id,
            TenantMemberModel.role == UserRole.ADMIN,
            TenantMemberModel.deleted.is_(False),
        )
        result = await self.session.execute(stmt)
        return result.scalar() or 0

    async def save(self, member: TenantMember) -> TenantMember:
        model = TenantMemberMapper.to_model(member)
        merged_model = await self.session.merge(model)
        await self.session.flush()
        await self.session.refresh(merged_model)
        return TenantMemberMapper.to_domain(merged_model, member.name, member.email)
