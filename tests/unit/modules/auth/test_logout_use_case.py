from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from security.dependencies.current_user import AuthContext
from modules.auth.application.use_cases.logout import LogoutUseCase
from tests.factories.user_factory import UserFactory


_UNSET = object()  # sentinela para diferenciar "não passado" de "passado como None"


def _make_auth_context(
    jti: str | None = "test-jti-1234",
    token_exp: int | None | object = _UNSET,
) -> AuthContext:
    """Helper que monta um AuthContext com valores padrão configuráveis.

    `token_exp=None` → AuthContext com token_exp=None (para testar ausência de exp).
    `token_exp` não informado → usa um exp 30 min no futuro (token válido).
    """
    if token_exp is _UNSET:
        # token expira daqui a 30 minutos (futuro) — padrão para testes de happy path
        resolved_exp: int | None = int(datetime.now(timezone.utc).timestamp()) + 1800
    else:
        resolved_exp = token_exp  # type: ignore[assignment]
    return AuthContext(
        user=UserFactory.make(),
        tenant_id=None,
        role=None,
        jti=jti,
        token_exp=resolved_exp,
    )


class TestLogoutUseCase:
    """Testes unitários para LogoutUseCase.

    Regras validadas:
    - jti + exp futuros → add_token_to_blacklist é chamada com os valores corretos
    - jti ausente → blacklist não é chamada
    - token_exp ausente → blacklist não é chamada
    - token já expirado (exp no passado) → remaining_seconds ≤ 0 → blacklist não é chamada
    """

    def setup_method(self) -> None:
        self.use_case = LogoutUseCase()

    async def test_logout_blacklists_token_when_jti_and_exp_are_present(self) -> None:
        """Token válido com jti e exp futuros → chama add_token_to_blacklist."""
        auth_context = _make_auth_context()

        with patch(
            "modules.auth.application.use_cases.logout.add_token_to_blacklist",
            new_callable=AsyncMock,
        ) as mock_blacklist:
            await self.use_case.execute(auth_context)

        mock_blacklist.assert_called_once()
        call_kwargs = mock_blacklist.call_args.kwargs
        assert call_kwargs["jti"] == "test-jti-1234"
        assert call_kwargs["expire_seconds"] > 0

    async def test_logout_does_nothing_when_jti_is_missing(self) -> None:
        """Sem jti → blacklist não é acionada."""
        auth_context = _make_auth_context(jti=None)

        with patch(
            "modules.auth.application.use_cases.logout.add_token_to_blacklist",
            new_callable=AsyncMock,
        ) as mock_blacklist:
            await self.use_case.execute(auth_context)

        mock_blacklist.assert_not_called()

    async def test_logout_does_nothing_when_token_exp_is_missing(self) -> None:
        """Sem token_exp → blacklist não é acionada."""
        auth_context = _make_auth_context(token_exp=None)

        with patch(
            "modules.auth.application.use_cases.logout.add_token_to_blacklist",
            new_callable=AsyncMock,
        ) as mock_blacklist:
            await self.use_case.execute(auth_context)

        mock_blacklist.assert_not_called()

    async def test_logout_does_nothing_when_token_is_already_expired(self) -> None:
        """Token já expirado (exp no passado) → remaining_seconds ≤ 0 → blacklist não é chamada."""
        past_exp = int(datetime.now(timezone.utc).timestamp()) - 60  # 1 min atrás
        auth_context = _make_auth_context(token_exp=past_exp)

        with patch(
            "modules.auth.application.use_cases.logout.add_token_to_blacklist",
            new_callable=AsyncMock,
        ) as mock_blacklist:
            await self.use_case.execute(auth_context)

        mock_blacklist.assert_not_called()
