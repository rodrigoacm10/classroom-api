from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from shared.enums.session_status import SessionStatus


class CreateAttendanceSessionRequest(BaseModel):
    room_id: UUID | None = Field(default=None, description="ID da sala para a chamada (opcional, utiliza a sala padrão da turma se omitido)")
    duration_minutes: int = Field(default=15, gt=0, le=1440, description="Duração da chamada em minutos (de 1 a 1440 - máximo 24 horas)")


class SubjectClassSummaryResponse(BaseModel):
    id: UUID
    name: str
    discipline_name: str

    model_config = {"from_attributes": True}


class RoomSummaryResponse(BaseModel):
    id: UUID
    name: str

    model_config = {"from_attributes": True}


class AttendanceSessionResponse(BaseModel):
    id: UUID
    subject_class_id: UUID
    room_id: UUID | None
    subject_class: SubjectClassSummaryResponse | None = None
    room: RoomSummaryResponse | None = None
    day_code: str
    opened_at: datetime
    expires_at: datetime
    closed_at: datetime | None
    status: SessionStatus
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
