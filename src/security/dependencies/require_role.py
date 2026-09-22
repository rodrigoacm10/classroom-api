from fastapi import Depends, HTTPException, status

from security.dependencies.current_user import AuthContext, get_auth_context
from shared.enums.user_role import UserRole


def require_role(*roles: UserRole):
    """
    Exige que o token tenha contexto de tenant E que a role seja uma das permitidas.

    Uso no router:
        @router.post("/sessions", dependencies=[Depends(require_role(UserRole.PROFESSOR))])
    """
    async def dependency(ctx: AuthContext = Depends(get_auth_context)) -> AuthContext:
        if ctx.tenant_id is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Nenhuma tenant selecionada. Use POST /auth/switch-tenant.",
            )
        if ctx.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Acesso não autorizado para este perfil.",
            )
        return ctx

    return dependency
