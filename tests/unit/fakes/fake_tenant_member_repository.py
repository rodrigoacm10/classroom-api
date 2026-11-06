from datetime import datetime
from uuid import UUID

from modules.tenant.domain.entities.members_metrics import MembersMetrics
from modules.tenant.domain.entities.students_metrics import StudentsMetrics
from modules.tenant.domain.entities.tenant_member import TenantMember
from shared.enums.user_role import UserRole
from shared.pagination import Page, PaginationParams, paginate_list


class FakeTenantMemberRepository:
    """
    Implementação em memória do TenantMemberRepository.
    Satisfaz o Protocol sem tocar em banco de dados.
    Usado exclusivamente em testes unitários.
    """

    def __init__(self) -> None:
        self._store: dict[UUID, TenantMember] = {}

    async def find_by_id(
        self, member_id: UUID, include_deleted: bool = False
    ) -> TenantMember | None:
        m = self._store.get(member_id)
        if m and (include_deleted or not m.deleted):
            return m
        return None

    async def find_by_tenant_and_user(
        self,
        tenant_id: UUID,
        user_id: UUID,
        include_deleted: bool = False,
    ) -> TenantMember | None:
        return next(
            (
                m
                for m in self._store.values()
                if m.tenant_id == tenant_id
                and m.user_id == user_id
                and (include_deleted or not m.deleted)
            ),
            None,
        )

    async def find_by_user_id(
        self, user_id: UUID, include_deleted: bool = False
    ) -> list[TenantMember]:
        return [
            m
            for m in self._store.values()
            if m.user_id == user_id and (include_deleted or not m.deleted)
        ]

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
        results = []
        for m in self._store.values():
            if m.tenant_id != tenant_id:
                continue
            if not include_deleted and m.deleted:
                continue
            if role is not None and m.role != role:
                continue
            if exclude_role is not None and m.role == exclude_role:
                continue
            if created_after is not None and m.created_at < created_after:
                continue
            if created_before is not None and m.created_at > created_before:
                continue
            if (
                subject_class_id is not None
                and getattr(m, "_subject_class_id", None) != subject_class_id
            ):
                continue
            if search is not None:
                search_lower = search.lower()
                user_name = (m.name or getattr(m, "_user_name", "")).lower()
                user_email = (m.email or getattr(m, "_user_email", "")).lower()
                if search_lower not in user_name and search_lower not in user_email:
                    continue
            results.append(m)
        return paginate_list(results, pagination)

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
        results = []
        for m in self._store.values():
            if m.tenant_id != tenant_id:
                continue
            if not include_deleted and m.deleted:
                continue
            if m.role != UserRole.ALUNO:
                continue
            if (
                subject_class_id is not None
                and getattr(m, "_subject_class_id", None) != subject_class_id
            ):
                continue
            if search is not None:
                search_lower = search.lower()
                user_name = (m.name or getattr(m, "_user_name", "")).lower()
                user_email = (m.email or getattr(m, "_user_email", "")).lower()
                if search_lower not in user_name and search_lower not in user_email:
                    continue
            turmas_count = getattr(m, "turmas_count", 0)
            if status == "regular" and turmas_count <= 0:
                continue
            if status == "sem_turma" and turmas_count > 0:
                continue
            results.append(m)

        is_asc = order.lower() == "asc"
        if sort_by == "name":
            results.sort(
                key=lambda x: (x.name or getattr(x, "_user_name", "")).lower(),
                reverse=not is_asc,
            )
        elif sort_by == "turmas_count":
            results.sort(
                key=lambda x: getattr(x, "turmas_count", 0),
                reverse=not is_asc,
            )

        return paginate_list(results, pagination)

    async def find_student_with_metrics_by_id(
        self,
        tenant_id: UUID,
        student_id: UUID,
        professor_user_id: UUID | None = None,
        include_deleted: bool = False,
    ) -> TenantMember | None:
        m = self._store.get(student_id)
        if not m or m.tenant_id != tenant_id or m.role != UserRole.ALUNO:
            return None
        if not include_deleted and m.deleted:
            return None
        return m

    async def get_students_metrics(
        self,
        tenant_id: UUID,
        professor_user_id: UUID | None = None,
    ) -> StudentsMetrics:
        students = [
            m
            for m in self._store.values()
            if m.tenant_id == tenant_id and m.role == UserRole.ALUNO and not m.deleted
        ]
        total_students = len(students)
        total_enrollments = sum(getattr(m, "turmas_count", 0) for m in students)
        avg_classes = total_enrollments / total_students if total_students > 0 else 0.0
        students_no_class = sum(1 for m in students if getattr(m, "turmas_count", 0) == 0)
        return StudentsMetrics(
            total_students=total_students,
            avg_classes_per_student=avg_classes,
            total_enrollments=total_enrollments,
            average_attendance_rate=0.0,
            students_at_risk=0,
            students_no_class=students_no_class,
        )

    async def get_members_metrics(self, tenant_id: UUID) -> MembersMetrics:
        members = [
            m
            for m in self._store.values()
            if m.tenant_id == tenant_id and m.role != UserRole.ALUNO and not m.deleted
        ]
        professors = sum(1 for m in members if m.role == UserRole.PROFESSOR)
        coordinators = sum(1 for m in members if m.role == UserRole.COORDENADOR)
        admins = sum(1 for m in members if m.role == UserRole.ADMIN)
        assigned_classes = sum(getattr(m, "assigned_classes_count", 0) for m in members)

        return MembersMetrics(
            total_members=len(members),
            professors_count=professors,
            coordinators_count=coordinators,
            admins_count=admins,
            management_count=admins + coordinators,
            assigned_classes_count=assigned_classes,
        )

    async def count_active_admins(self, tenant_id: UUID) -> int:
        return len(
            [
                m
                for m in self._store.values()
                if m.tenant_id == tenant_id and m.role == UserRole.ADMIN and not m.deleted
            ]
        )

    async def save(self, member: TenantMember) -> TenantMember:
        self._store[member.id] = member
        return member

    # ─── helpers de setup ────────────────────────────────────────────────────

    def seed(self, member: TenantMember) -> None:
        """Pré-popula o repositório com um membro sem passar pelo save assíncrono."""
        self._store[member.id] = member
