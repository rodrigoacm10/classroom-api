from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr

from shared.enums.user_role import UserRole


class CreateTenantRequest(BaseModel):
    name: str
    slug: str


class TenantResponse(BaseModel):
    id: UUID
    name: str
    slug: str
    active: bool
    deleted: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class MyTenantResponse(BaseModel):
    id: UUID
    name: str
    slug: str
    active: bool
    deleted: bool
    role: UserRole
    created_at: datetime

    model_config = {"from_attributes": True}


class AddTenantMemberRequest(BaseModel):
    user_id: UUID
    role: UserRole


class TenantMemberResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    user_id: UUID
    role: UserRole
    created_at: datetime

    model_config = {"from_attributes": True}


class SendInviteRequest(BaseModel):
    email: EmailStr
    role: UserRole


class InviteStatusResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    tenant_name: str
    email: str
    role: UserRole
    token: str
    status: Literal["pending", "accepted", "expired"]
    expires_at: datetime
    created_at: datetime

    model_config = {"from_attributes": True}
