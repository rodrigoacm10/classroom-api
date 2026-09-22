from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from infra.database.session import get_db
from modules.notification.application.use_cases.register_fcm_token import (
    RegisterFCMTokenInput,
    RegisterFCMTokenUseCase,
)
from modules.notification.application.use_cases.remove_fcm_token import (
    RemoveFCMTokenInput,
    RemoveFCMTokenUseCase,
)
from modules.notification.infra.repositories.fcm_token_sqlalchemy_repository import (
    FCMTokenSQLAlchemyRepository,
)
from modules.notification.interface.schemas.fcm_token_schemas import (
    FCMTokenResponse,
    RegisterFCMTokenRequest,
)
from modules.tenant.infra.repositories.tenant_member_sqlalchemy_repository import (
    TenantMemberSQLAlchemyRepository,
)
from modules.tenant.infra.repositories.tenant_sqlalchemy_repository import (
    TenantSQLAlchemyRepository,
)
from security.dependencies.current_user import AuthContext, get_auth_context

router = APIRouter(
    prefix="/tenants/{tenant_id}/fcm-tokens",
    tags=["notifications"],
)


@router.post("", response_model=FCMTokenResponse, status_code=status.HTTP_200_OK)
async def register_fcm_token(
    tenant_id: UUID,
    body: RegisterFCMTokenRequest,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
) -> FCMTokenResponse:
    """Registra ou atualiza (upsert) o token FCM do dispositivo do usuário."""
    fcm_token_repo = FCMTokenSQLAlchemyRepository(session=db)
    tenant_repo = TenantSQLAlchemyRepository(session=db)
    member_repo = TenantMemberSQLAlchemyRepository(session=db)

    use_case = RegisterFCMTokenUseCase(
        fcm_token_repo=fcm_token_repo,
        tenant_repo=tenant_repo,
        member_repo=member_repo,
    )

    token = await use_case.execute(
        RegisterFCMTokenInput(
            tenant_id=tenant_id,
            user_id=auth.user.id,
            user_role=auth.role,
            device_id=body.device_id,
            fcm_token=body.fcm_token,
            platform=body.platform,
            app_version=body.app_version,
        )
    )

    return FCMTokenResponse.model_validate(token)


@router.delete("/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_fcm_token(
    tenant_id: UUID,
    device_id: str,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Remove o token FCM do dispositivo associado ao usuário ao realizar logout."""
    fcm_token_repo = FCMTokenSQLAlchemyRepository(session=db)
    tenant_repo = TenantSQLAlchemyRepository(session=db)
    member_repo = TenantMemberSQLAlchemyRepository(session=db)

    use_case = RemoveFCMTokenUseCase(
        fcm_token_repo=fcm_token_repo,
        tenant_repo=tenant_repo,
        member_repo=member_repo,
    )

    await use_case.execute(
        RemoveFCMTokenInput(
            tenant_id=tenant_id,
            user_id=auth.user.id,
            user_role=auth.role,
            device_id=device_id,
        )
    )
