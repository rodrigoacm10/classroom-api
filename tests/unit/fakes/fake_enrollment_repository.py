from datetime import datetime, timezone
from uuid import UUID

from modules.enrollment.domain.entities.enrollment import Enrollment
from shared.enums.drop_reason import DropReason
from shared.enums.enrollment_status import EnrollmentStatus


class FakeEnrollmentRepository:

    def __init__(self) -> None:
        self._enrollments: dict[UUID, Enrollment] = {}

    async def save(self, enrollment: Enrollment) -> Enrollment:
        self._enrollments[enrollment.id] = enrollment
        return enrollment

    async def find_by_id(
        self, enrollment_id: UUID, include_deleted: bool = False
    ) -> Enrollment | None:
        e = self._enrollments.get(enrollment_id)
        if e and (include_deleted or not e.deleted):
            return e
        return None

    async def find_by_class_and_member(
        self,
        subject_class_id: UUID,
        tenant_member_id: UUID,
        include_deleted: bool = False,
    ) -> Enrollment | None:
        return next(
            (
                e
                for e in self._enrollments.values()
                if e.subject_class_id == subject_class_id
                and e.tenant_member_id == tenant_member_id
                and (include_deleted or not e.deleted)
            ),
            None,
        )

    async def list_by_subject_class(
        self,
        subject_class_id: UUID,
        status: EnrollmentStatus | None = None,
        include_deleted: bool = False,
    ) -> list[Enrollment]:
        result = []
        for e in self._enrollments.values():
            if e.subject_class_id != subject_class_id:
                continue
            if not include_deleted and e.deleted:
                continue
            if status is not None and e.status != status:
                continue
            result.append(e)
        return result

    async def list_by_member(
        self,
        tenant_member_id: UUID,
        status: EnrollmentStatus | None = None,
        include_deleted: bool = False,
    ) -> list[Enrollment]:
        result = []
        for e in self._enrollments.values():
            if e.tenant_member_id != tenant_member_id:
                continue
            if not include_deleted and e.deleted:
                continue
            if status is not None and e.status != status:
                continue
            result.append(e)
        return result

    async def drop_all_active_for_member(self, tenant_member_id: UUID) -> int:
        count = 0
        for e in self._enrollments.values():
            if (
                e.tenant_member_id == tenant_member_id
                and e.status == EnrollmentStatus.ACTIVE
                and not e.deleted
            ):
                e.status = EnrollmentStatus.DROPPED
                e.dropped_at = datetime.now(timezone.utc)
                e.drop_reason = DropReason.ROLE_CHANGE
                count += 1
        return count
