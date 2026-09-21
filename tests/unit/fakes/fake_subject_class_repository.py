from uuid import UUID

from modules.subject_class.domain.entities.subject_class import SubjectClass
from modules.subject_class.domain.entities.subject_class_summary import SubjectClassSummary


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

    async def list_by_tenant(
        self, tenant_id: UUID, include_deleted: bool = False
    ) -> list[SubjectClass]:
        return [
            c for c in self._classes.values()
            if c.tenant_id == tenant_id and (include_deleted or not c.deleted)
        ]

    async def list_summaries_by_tenant(
        self,
        tenant_id: UUID,
        include_deleted: bool = False,
        professor_id: UUID | None = None,
        room_id: UUID | None = None,
    ) -> list[SubjectClassSummary]:
        classes = await self.list_by_tenant(tenant_id, include_deleted=include_deleted)
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
                name=c.name,
                discipline_name=c.discipline_name,
                student_count=0,
                attendance_rate=0.0,
                created_at=c.created_at,
                updated_at=c.updated_at,
            )
            for c in classes
        ]

    async def delete(self, subject_class: SubjectClass) -> None:
        subject_class.deleted = True
        await self.save(subject_class)
