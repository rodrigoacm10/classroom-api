from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from shared.enums.session_status import SessionStatus


class CreateAttendanceSessionRequest(BaseModel):
    room_id: UUID | None = Field(
        default=None,
        description="ID da sala para a chamada (opcional, utiliza a sala padrão da turma se omitido)",
    )
    duration_minutes: int = Field(
        default=15,
        gt=0,
        le=1440,
        description="Duração da chamada em minutos (de 1 a 1440 - máximo 24 horas)",
    )


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
    duration_minutes: int
    total_students: int
    confirmed_count: int
    irregular_count: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ActiveAttendanceSessionResponse(BaseModel):
    session_id: UUID
    subject_class_id: UUID
    subject_class_name: str
    discipline_name: str
    day_code: str
    room_id: UUID | None = None
    room_name: str | None = None
    opened_at: datetime
    expires_at: datetime
    duration_minutes: int
    present_count: int
    total_students: int

    model_config = {"from_attributes": True}


class LastSessionSummaryResponse(BaseModel):
    id: UUID
    subject_class_id: UUID
    subject_class_name: str
    discipline_name: str
    room_name: str | None = None
    opened_at: datetime
    day_code: str
    status: SessionStatus
    confirmed_count: int
    total_students: int
    attendance_rate: float

    model_config = {"from_attributes": True}


class AttendanceMetricsResponse(BaseModel):
    total_sessions: int = Field(..., description="Total de chamadas nos últimos N dias")
    average_attendance_rate: float = Field(..., description="Frequência média agregada (0.0 a 1.0)")
    cancelled_sessions: int = Field(..., description="Total de chamadas canceladas nos últimos N dias")
    last_session: LastSessionSummaryResponse | None = Field(default=None, description="Última chamada realizada")

    model_config = {"from_attributes": True}
