from uuid import UUID

from modules.subject_class.domain.entities.subject_class import SubjectClass


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

    async def delete(self, subject_class: SubjectClass) -> None:
        subject_class.deleted = True
        await self.save(subject_class)
