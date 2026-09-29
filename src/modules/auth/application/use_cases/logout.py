from datetime import datetime, timezone

from security.blacklist import add_token_to_blacklist
from security.dependencies.current_user import AuthContext
from security.jwt import decode_access_token


class LogoutUseCase:
    async def execute(
        self,
        auth_context: AuthContext | None = None,
        refresh_token: str | None = None,
    ) -> None:
        now = int(datetime.now(timezone.utc).timestamp())

        # 1. Invalida o Access Token no Redis (se presente)
        if auth_context and auth_context.jti and auth_context.token_exp:
            remaining_seconds = auth_context.token_exp - now
            if remaining_seconds > 0:
                await add_token_to_blacklist(
                    jti=auth_context.jti,
                    expire_seconds=remaining_seconds,
                )

        # 2. Invalida o Refresh Token no Redis (se fornecido via cookie ou body)
        if refresh_token:
            try:
                payload = decode_access_token(refresh_token)
                refresh_jti = payload.get("jti")
                refresh_exp = payload.get("exp")
                if refresh_jti and refresh_exp:
                    remaining_refresh = refresh_exp - now
                    if remaining_refresh > 0:
                        await add_token_to_blacklist(
                            jti=refresh_jti,
                            expire_seconds=remaining_refresh,
                        )
            except Exception:
                pass
