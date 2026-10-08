from uuid import UUID

from modules.subject_class.domain.entities.subject_class import SubjectClass
from modules.subject_class.domain.entities.subject_class_metrics import SubjectClassMetrics
from modules.subject_class.domain.entities.subject_class_summary import SubjectClassSummary
from shared.pagination import Page, PaginationParams, paginate_list


class FakeSubjectClassRepository:
    def __init__(self) -> None:
        self._classes: dict[UUID, SubjectClass] = {}

    async def save(self, subject_class: SubjectClass) -> SubjectClass:
        self._classes[subject_class.id] = subject_class
        return subject_class

    async def find_by_id(
        self, subject_class_id: UUID, include_deleted: bool = False
    ) -> SubjectClass | None:
        c = self._classes.get(subject_class_id)
        if c and (include_deleted or not c.deleted):
            return c
        return None

    async def find_by_id_and_tenant(
        self, subject_class_id: UUID, tenant_id: UUID, include_deleted: bool = False
    ) -> SubjectClass | None:
        c = self._classes.get(subject_class_id)
        if c and c.tenant_id == tenant_id and (include_deleted or not c.deleted):
            return c
        return None

    async def find_summary_by_id_and_tenant(
        self, subject_class_id: UUID, tenant_id: UUID, include_deleted: bool = False
    ) -> SubjectClassSummary | None:
        c = await self.find_by_id_and_tenant(subject_class_id, tenant_id, include_deleted)
        if not c:
            return None
        return SubjectClassSummary(
            id=c.id,
            tenant_id=c.tenant_id,
            professor_id=c.professor_id,
            professor_name="Prof. Teste" if c.professor_id else None,
            room_id=c.room_id,
            room_name="Sala Teste" if c.room_id else None,
            has_active_session=False,
            active_session_id=None,
            name=c.name,
            discipline_name=c.discipline_name,
            active=c.active,
            student_count=0,
            attendance_rate=0.0,
            created_at=c.created_at,
            updated_at=c.updated_at,
        )

    async def list_by_tenant(
        self,
        tenant_id: UUID,
        include_deleted: bool = False,
        active: bool | None = None,
    ) -> list[SubjectClass]:
        return [
            c
            for c in self._classes.values()
            if c.tenant_id == tenant_id
            and (include_deleted or not c.deleted)
            and (active is None or c.active == active)
        ]

    async def list_summaries_by_tenant(
        self,
        tenant_id: UUID,
        include_deleted: bool = False,
        professor_id: UUID | None = None,
        room_id: UUID | None = None,
        active: bool | None = None,
        days: int | None = None,
    ) -> list[SubjectClassSummary]:
        classes = await self.list_by_tenant(
            tenant_id, include_deleted=include_deleted, active=active
        )
        if professor_id is not None:
            classes = [c for c in classes if c.professor_id == professor_id]
        if room_id is not None:
            classes = [c for c in classes if c.room_id == room_id]
        return [
            SubjectClassSummary(
                id=c.id,
                tenant_id=c.tenant_id,
                professor_id=c.professor_id,
                professor_name=None,
                room_id=c.room_id,
                room_name=None,
                has_active_session=False,
                active_session_id=None,
                name=c.name,
                discipline_name=c.discipline_name,
                active=c.active,
                student_count=0,
                attendance_rate=0.0,
                created_at=c.created_at,
                updated_at=c.updated_at,
            )
            for c in classes
        ]

    async def find_summaries_by_tenant_paginated(
        self,
        tenant_id: UUID,
        pagination: PaginationParams,
        include_deleted: bool = False,
        professor_id: UUID | None = None,
        room_id: UUID | None = None,
        search: str | None = None,
        active: bool | None = None,
        has_active_session: bool | None = None,
        sort_by: str | None = None,
        order: str | None = None,
    ) -> Page[SubjectClassSummary]:
        summaries = await self.list_summaries_by_tenant(
            tenant_id=tenant_id,
            include_deleted=include_deleted,
            professor_id=professor_id,
            room_id=room_id,
            active=active,
        )
        if search:
            s = search.lower()
            summaries = [
                sm for sm in summaries if s in sm.name.lower() or s in sm.discipline_name.lower()
            ]
        if has_active_session is not None:
            summaries = [sm for sm in summaries if sm.has_active_session == has_active_session]

        parsed_sort = (sort_by or "").lower().strip()
        parsed_order = (order or "asc").lower().strip()
        if parsed_sort.endswith("_asc"):
            parsed_sort = parsed_sort[:-4]
            parsed_order = "asc"
        elif parsed_sort.endswith("_desc"):
            parsed_sort = parsed_sort[:-5]
            parsed_order = "desc"

        reverse = parsed_order == "desc"
        if parsed_sort == "name":
            summaries.sort(key=lambda sm: sm.name.lower(), reverse=reverse)
        elif parsed_sort in ("discipline", "discipline_name"):
            summaries.sort(key=lambda sm: sm.discipline_name.lower(), reverse=reverse)
        elif parsed_sort in ("students", "student_count"):
            summaries.sort(key=lambda sm: sm.student_count, reverse=reverse)
        elif parsed_sort == "created_at":
            summaries.sort(key=lambda sm: sm.created_at, reverse=reverse)
        else:
            summaries.sort(key=lambda sm: sm.created_at, reverse=True)

        return paginate_list(summaries, pagination)

    async def get_metrics_by_tenant(
        self,
        tenant_id: UUID,
        professor_id: UUID | None = None,
        days: int | None = None,
    ) -> SubjectClassMetrics:
        summaries = await self.list_summaries_by_tenant(
            tenant_id=tenant_id,
            professor_id=professor_id,
            days=days,
        )
        total_classes = len(summaries)
        active_classes = sum(1 for s in summaries if s.active)
        inactive_classes = total_classes - active_classes
        total_students = sum(s.student_count for s in summaries)
        active_summaries = [s for s in summaries if s.active]
        avg_attendance = (
            round(sum(s.attendance_rate for s in active_summaries) / len(active_summaries), 4)
            if active_summaries
            else 0.0
        )
        at_risk_count = sum(1 for s in active_summaries if s.attendance_rate < 0.75)
        live_classes_count = sum(1 for s in summaries if s.has_active_session)

        return SubjectClassMetrics(
            total_classes=total_classes,
            active_classes=active_classes,
            inactive_classes=inactive_classes,
            total_students=total_students,
            average_attendance_rate=avg_attendance,
            at_risk_classes_count=at_risk_count,
            live_classes_count=live_classes_count,
        )

    async def delete(self, subject_class: SubjectClass) -> None:
        subject_class.deleted = True
        await self.save(subject_class)
