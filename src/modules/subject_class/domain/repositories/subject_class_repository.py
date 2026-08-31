from typing import Protocol
from uuid import UUID

from modules.subject_class.domain.entities.subject_class import SubjectClass


class SubjectClassRepository(Protocol):

    async def save(self, subject_class: SubjectClass) -> SubjectClass: ...

    async def find_by_id(
        self, subject_class_id: UUID, include_deleted: bool = False
    ) -> SubjectClass | None: ...

    async def find_by_id_and_tenant(
        self, subject_class_id: UUID, tenant_id: UUID, include_deleted: bool = False
    ) -> SubjectClass | None: ...

    async def list_by_tenant(
        self, tenant_id: UUID, include_deleted: bool = False
    ) -> list[SubjectClass]: ...

    async def delete(self, subject_class: SubjectClass) -> None: ...
