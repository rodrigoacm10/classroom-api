from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr

from shared.enums.user_role import UserRole


class CreateUserRequest(BaseModel):
    name: str
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: UUID
    name: str
    email: str
    tenant_id: UUID | None = None
    role: UserRole | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
