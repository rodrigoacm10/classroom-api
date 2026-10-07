from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class CreateSubjectClassRequest(BaseModel):
    room_id: UUID = Field(..., description="ID da sala física onde a turma ocorre.")
    name: str = Field(..., min_length=1, max_length=255, examples=["Turma A — Noturno"])
    discipline_name: str = Field(..., min_length=1, max_length=255, examples=["Banco de Dados"])


class UpdateSubjectClassRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    discipline_name: str | None = Field(default=None, min_length=1, max_length=255)
    room_id: UUID | None = Field(default=None, description="Alterar a sala vinculada à turma.")
    active: bool | None = Field(default=None, description="Ativar ou desativar/encerrar a turma.")


class SubjectClassResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    professor_id: UUID | None
    room_id: UUID | None
    name: str
    discipline_name: str
    active: bool = True
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SubjectClassListItemResponse(SubjectClassResponse):
    professor_name: str | None = None
    room_name: str | None = None
    has_active_session: bool = False
    active_session_id: UUID | None = None
    student_count: int
    attendance_rate: float


class SubjectClassMetricsResponse(BaseModel):
    total_classes: int = Field(..., description="Total de turmas cadastradas")
    active_classes: int = Field(..., description="Total de turmas ativas")
    inactive_classes: int = Field(..., description="Total de turmas inativas")
    total_students: int = Field(..., description="Total de alunos matriculados nas turmas")
    average_attendance_rate: float = Field(..., description="Taxa de frequência média das turmas ativas (0.0 a 1.0)")
    at_risk_classes_count: int = Field(..., description="Quantidade de turmas com frequência abaixo de 75%")
    live_classes_count: int = Field(..., description="Quantidade de turmas com sessão de chamada aberta agora")

    model_config = {"from_attributes": True}

