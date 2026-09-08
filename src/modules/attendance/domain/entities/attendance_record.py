from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID, uuid4

from shared.enums.record_status import RecordStatus


@dataclass
class AttendanceRecord:
    session_id: UUID
    tenant_member_id: UUID
    latitude: float
    longitude: float
    distance_meters: float
    within_radius: bool
    gps_accuracy_meters: float | None = None
    record_status: RecordStatus = RecordStatus.REGULAR
    irregularity_flags: list[str] = field(default_factory=list)
    reviewed_by: UUID | None = None
    reviewed_at: datetime | None = None
    review_note: str | None = None
    device_id: str | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    device_info: dict | None = None
    evidence_photo_url: str | None = None
    confirmed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    id: UUID = field(default_factory=uuid4)

    def approve(self, reviewed_by: UUID, note: str | None = None) -> None:
        self.record_status = RecordStatus.APPROVED
        self.reviewed_by = reviewed_by
        self.reviewed_at = datetime.now(timezone.utc)
        self.review_note = note

    def reject(self, reviewed_by: UUID, note: str | None = None) -> None:
        self.record_status = RecordStatus.REJECTED
        self.reviewed_by = reviewed_by
        self.reviewed_at = datetime.now(timezone.utc)
        self.review_note = note
