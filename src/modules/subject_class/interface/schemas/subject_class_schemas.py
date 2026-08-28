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


class SubjectClassResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    professor_id: UUID | None
    room_id: UUID | None
    name: str
    discipline_name: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
