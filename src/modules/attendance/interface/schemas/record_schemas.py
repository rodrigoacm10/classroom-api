from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from shared.enums.record_status import RecordStatus


class ConfirmAttendanceRequest(BaseModel):
    day_code: str = Field(..., min_length=1, max_length=10, description="Código de 6 caracteres alfanuméricos exibido pelo professor")
    latitude: float = Field(..., ge=-90.0, le=90.0, description="Latitude do dispositivo (WGS84)")
    longitude: float = Field(..., ge=-180.0, le=180.0, description="Longitude do dispositivo (WGS84)")
    gps_accuracy_meters: float | None = Field(default=None, ge=0.0, description="Precisão do GPS em metros relatada pelo dispositivo")
    device_id: str | None = Field(default=None, max_length=64, description="Identificador único do dispositivo")
    device_info: dict | None = Field(default=None, description="Metadados do dispositivo (sistema operacional, modelo, etc.)")


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
