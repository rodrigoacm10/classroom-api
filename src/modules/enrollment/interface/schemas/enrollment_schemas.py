from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, computed_field

from shared.enums.drop_reason import DropReason
from shared.enums.enrollment_status import EnrollmentStatus


class EnrollStudentRequest(BaseModel):
    tenant_member_id: UUID


class EnrollmentResponse(BaseModel):
    id: UUID
    subject_class_id: UUID
    tenant_member_id: UUID
    status: EnrollmentStatus
    enrolled_at: datetime
    dropped_at: datetime | None = None
    deleted_at: datetime | None = None
    drop_reason: DropReason | None = None

    model_config = ConfigDict(from_attributes=True)


class StudentSubjectClassListItemResponse(BaseModel):
    enrollment_id: UUID
    subject_class_id: UUID
    name: str
    discipline_name: str
    room_id: UUID | None
    room_name: str | None
    professor_id: UUID | None
    professor_name: str | None
    attendance_rate: float
    status: EnrollmentStatus
    total_sessions: int = 0
    absences_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class StudentMetricsResponse(BaseModel):
    total_classes: int = Field(
        ..., description="Total de turmas ativas em que o aluno está matriculado"
    )
    average_attendance_rate: float = Field(
        ..., description="Taxa média de frequência entre as turmas (0.0 a 1.0)"
    )
    at_risk_count: int = Field(..., description="Quantidade de turmas com frequência abaixo de 75%")

    @computed_field  # type: ignore[misc]
    @property
    def classes_count(self) -> int:
        return self.total_classes

    model_config = ConfigDict(from_attributes=True)
