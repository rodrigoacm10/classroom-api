from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from shared.enums.record_status import RecordStatus


class ReviewAttendanceRecordRequest(BaseModel):
    decision: RecordStatus = Field(..., description="Decisão da revisão: 'approved' ou 'rejected'")
    note: str | None = Field(default=None, max_length=1000, description="Justificativa ou observação da revisão")


class AttendanceRecordResponse(BaseModel):
    id: UUID
    session_id: UUID
    tenant_member_id: UUID
    confirmed_at: datetime
    latitude: float
    longitude: float
    distance_meters: float
    within_radius: bool
    gps_accuracy_meters: float | None
    record_status: RecordStatus
    irregularity_flags: list[str]
    reviewed_by: UUID | None
    reviewed_at: datetime | None
    review_note: str | None
    device_id: str | None
    ip_address: str | None
    user_agent: str | None
    device_info: dict | None
    evidence_photo_url: str | None

    model_config = {"from_attributes": True}


class SessionRosterItemResponse(BaseModel):
    tenant_member_id: UUID
    student_name: str
    enrollment_id: UUID
    record_id: UUID | None = None
    confirmed_at: datetime | None = None
    distance_meters: float | None = None
    within_radius: bool | None = None
    record_status: RecordStatus | None = None

    model_config = {"from_attributes": True}
