from datetime import datetime, timezone

from security.blacklist import add_token_to_blacklist
from security.dependencies.current_user import AuthContext


class LogoutUseCase:

    async def execute(self, auth_context: AuthContext) -> None:
        if not auth_context.jti or not auth_context.token_exp:
            return

        now = int(datetime.now(timezone.utc).timestamp())
        remaining_seconds = auth_context.token_exp - now

        if remaining_seconds > 0:
            await add_token_to_blacklist(
                jti=auth_context.jti,
                expire_seconds=remaining_seconds,
            )
