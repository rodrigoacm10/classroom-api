from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class CreateRoomRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, examples=["Sala 204"])
    latitude: float = Field(
        ...,
        ge=-90.0,
        le=90.0,
        description="Latitude do ponto central da sala (WGS84 / GPS). Intervalo: -90.0 a 90.0.",
        examples=[-8.0476],
    )
    longitude: float = Field(
        ...,
        ge=-180.0,
        le=180.0,
        description="Longitude do ponto central da sala (WGS84 / GPS). Intervalo: -180.0 a 180.0.",
        examples=[-34.8770],
    )
    tolerance_radius_meters: int = Field(
        default=50,
        ge=5,
        le=500,
        description="Raio de tolerância em metros. Define a circunferência de presença válida ao redor do ponto central.",
        examples=[50],
    )


class UpdateRoomRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    latitude: float | None = Field(default=None, ge=-90.0, le=90.0)
    longitude: float | None = Field(default=None, ge=-180.0, le=180.0)
    tolerance_radius_meters: int | None = Field(default=None, ge=5, le=500)


class RoomResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    created_by: UUID | None
    name: str
    latitude: float
    longitude: float
    tolerance_radius_meters: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
