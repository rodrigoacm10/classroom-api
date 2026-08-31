from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID, uuid4

from shared.enums.enrollment_status import EnrollmentStatus


@dataclass
class Enrollment:
    subject_class_id: UUID
    tenant_member_id: UUID
    status: EnrollmentStatus = EnrollmentStatus.ACTIVE
    deleted: bool = False
    id: UUID = field(default_factory=uuid4)
    enrolled_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
