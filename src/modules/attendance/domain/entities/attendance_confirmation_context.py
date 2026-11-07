from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from shared.enums.enrollment_status import EnrollmentStatus
from shared.enums.session_status import SessionStatus


@dataclass
class AttendanceConfirmationContext:
    tenant_id: UUID
    tenant_deleted: bool
    subject_class_id: UUID
    subject_class_deleted: bool
    session_id: UUID
    session_status: SessionStatus
    session_expires_at: datetime
    session_day_code: str
    member_id: UUID | None
    member_deleted: bool
    enrollment_id: UUID | None
    enrollment_status: EnrollmentStatus | None
    enrollment_deleted: bool
    room_id: UUID | None
    room_tolerance_radius: float
    room_location: Any | None
    already_confirmed: bool
    shared_device_conflict: bool
