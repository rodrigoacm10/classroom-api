from datetime import datetime

from pydantic import BaseModel, Field


class RegisterFCMTokenRequest(BaseModel):
    device_id: str = Field(..., min_length=1, max_length=64)
    fcm_token: str = Field(..., min_length=1)
    platform: str = Field(..., pattern="^(android|ios)$")
    app_version: str | None = Field(default=None, max_length=20)


class FCMTokenResponse(BaseModel):
    device_id: str
    platform: str
    updated_at: datetime

    model_config = {"from_attributes": True}
