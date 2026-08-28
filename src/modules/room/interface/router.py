from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from infra.database.session import get_db
from modules.room.application.use_cases.create_room import CreateRoomInput, CreateRoomUseCase
from modules.room.application.use_cases.delete_room import DeleteRoomInput, DeleteRoomUseCase
from modules.room.application.use_cases.get_room import GetRoomInput, GetRoomUseCase
from modules.room.application.use_cases.list_rooms import ListRoomsInput, ListRoomsUseCase
from modules.room.application.use_cases.update_room import UpdateRoomInput, UpdateRoomUseCase
from modules.room.infra.repositories.room_sqlalchemy_repository import RoomSQLAlchemyRepository
from modules.room.interface.schemas.room_schemas import (
    CreateRoomRequest,
    RoomResponse,
    UpdateRoomRequest,
)
from modules.tenant.infra.repositories.tenant_sqlalchemy_repository import TenantSQLAlchemyRepository
from modules.user.domain.entities.user import User
from security.dependencies.current_user import get_current_user
from security.dependencies.require_role import require_role
from shared.enums.user_role import UserRole

router = APIRouter(prefix="/tenants/{tenant_id}/rooms", tags=["rooms"])


@router.post(
    "",
    response_model=RoomResponse,
    status_code=201,
    dependencies=[Depends(require_role(UserRole.ADMIN, UserRole.PROFESSOR))],
)
async def create_room(
    tenant_id: UUID,
    body: CreateRoomRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RoomResponse:
    """
    Cadastra uma nova sala para a Tenant/Instituição.
    O campo `location` é definido por `latitude` e `longitude` (coordenadas GPS / WGS84).
    O `tolerance_radius_meters` define o raio da circunferência de presença válida.
    """
    room_repo = RoomSQLAlchemyRepository(session=db)
    tenant_repo = TenantSQLAlchemyRepository(session=db)
    use_case = CreateRoomUseCase(room_repo=room_repo, tenant_repo=tenant_repo)

    room = await use_case.execute(
        CreateRoomInput(
            tenant_id=tenant_id,
            name=body.name,
            latitude=body.latitude,
            longitude=body.longitude,
            tolerance_radius_meters=body.tolerance_radius_meters,
            created_by=current_user.id,
        )
    )
    return RoomResponse(
        id=room.id,
        tenant_id=room.tenant_id,
        created_by=room.created_by,
        name=room.name,
        latitude=room.latitude,
        longitude=room.longitude,
        tolerance_radius_meters=room.tolerance_radius_meters,
        created_at=room.created_at,
        updated_at=room.updated_at,
    )


@router.get("", response_model=list[RoomResponse])
async def list_rooms(
    tenant_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> list[RoomResponse]:
    """Lista todas as salas de uma Tenant/Instituição."""
    room_repo = RoomSQLAlchemyRepository(session=db)
    tenant_repo = TenantSQLAlchemyRepository(session=db)
    use_case = ListRoomsUseCase(room_repo=room_repo, tenant_repo=tenant_repo)

    rooms = await use_case.execute(ListRoomsInput(tenant_id=tenant_id))
    return [
        RoomResponse(
            id=r.id,
            tenant_id=r.tenant_id,
            created_by=r.created_by,
            name=r.name,
            latitude=r.latitude,
            longitude=r.longitude,
            tolerance_radius_meters=r.tolerance_radius_meters,
            created_at=r.created_at,
            updated_at=r.updated_at,
        )
        for r in rooms
    ]


@router.get("/{room_id}", response_model=RoomResponse)
async def get_room(
    tenant_id: UUID,
    room_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> RoomResponse:
    """Retorna os detalhes de uma sala específica."""
    room_repo = RoomSQLAlchemyRepository(session=db)
    use_case = GetRoomUseCase(room_repo=room_repo)

    room = await use_case.execute(GetRoomInput(room_id=room_id, tenant_id=tenant_id))
    return RoomResponse(
        id=room.id,
        tenant_id=room.tenant_id,
        created_by=room.created_by,
        name=room.name,
        latitude=room.latitude,
        longitude=room.longitude,
        tolerance_radius_meters=room.tolerance_radius_meters,
        created_at=room.created_at,
        updated_at=room.updated_at,
    )


@router.patch(
    "/{room_id}",
    response_model=RoomResponse,
    dependencies=[Depends(require_role(UserRole.ADMIN, UserRole.PROFESSOR))],
)
async def update_room(
    tenant_id: UUID,
    room_id: UUID,
    body: UpdateRoomRequest,
    db: AsyncSession = Depends(get_db),
) -> RoomResponse:
    """Atualiza parcialmente os dados de uma sala. Apenas os campos enviados são modificados."""
    room_repo = RoomSQLAlchemyRepository(session=db)
    use_case = UpdateRoomUseCase(room_repo=room_repo)

    room = await use_case.execute(
        UpdateRoomInput(
            room_id=room_id,
            tenant_id=tenant_id,
            name=body.name,
            latitude=body.latitude,
            longitude=body.longitude,
            tolerance_radius_meters=body.tolerance_radius_meters,
        )
    )
    return RoomResponse(
        id=room.id,
        tenant_id=room.tenant_id,
        created_by=room.created_by,
        name=room.name,
        latitude=room.latitude,
        longitude=room.longitude,
        tolerance_radius_meters=room.tolerance_radius_meters,
        created_at=room.created_at,
        updated_at=room.updated_at,
    )


@router.delete(
    "/{room_id}",
    status_code=204,
    dependencies=[Depends(require_role(UserRole.ADMIN))],
)
async def delete_room(
    tenant_id: UUID,
    room_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Remove permanentemente uma sala da Tenant. Requer papel de ADMIN."""
    room_repo = RoomSQLAlchemyRepository(session=db)
    use_case = DeleteRoomUseCase(room_repo=room_repo)

    await use_case.execute(DeleteRoomInput(room_id=room_id, tenant_id=tenant_id))
