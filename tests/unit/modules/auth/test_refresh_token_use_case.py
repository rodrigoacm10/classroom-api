import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import jwt
import pytest

from modules.auth.application.use_cases.refresh_token import (
    RefreshTokenInput,
    RefreshTokenUseCase,
)
from tests.factories.user_factory import UserFactory
from tests.unit.fakes.fake_user_repository import FakeUserRepository


def _make_valid_payload(user_id: uuid.UUID, token_type: str = "refresh") -> dict:
    """Payload JWT decodificado simulando um token refresh válido."""
    return {
        "jti": str(uuid.uuid4()),
        "sub": str(user_id),
        "type": token_type,
    }


class TestRefreshTokenUseCase:
    """Testes unitários para RefreshTokenUseCase.

    Regras validadas:
    - Token refresh válido + usuário existe → retorna novos tokens
    - Token expirado (jwt.ExpiredSignatureError) → ValueError
    - Token inválido (jwt.InvalidTokenError) → ValueError
    - Token com type != 'refresh' → ValueError
    - JTI na blacklist → ValueError
    - Usuário não encontrado (deletado) → ValueError
    """

    def setup_method(self) -> None:
        self.repo = FakeUserRepository()
        self.use_case = RefreshTokenUseCase(user_repo=self.repo)

    async def test_refresh_returns_new_tokens_on_valid_refresh_token(self) -> None:
        """Token refresh válido e usuário existente → access + refresh novos retornados."""
        user = UserFactory.make()
        self.repo.seed(user)
        payload = _make_valid_payload(user.id, token_type="refresh")

        with (
            patch(
                "modules.auth.application.use_cases.refresh_token.decode_access_token",
                return_value=payload,
            ),
            patch(
                "modules.auth.application.use_cases.refresh_token.is_token_blacklisted",
                new_callable=AsyncMock,
                return_value=False,
            ),
        ):
            result = await self.use_case.execute(
                RefreshTokenInput(refresh_token="valid.refresh.token")
            )

        assert result.access_token
        assert result.refresh_token
        assert result.token_type == "bearer"

    async def test_refresh_raises_when_token_is_expired(self) -> None:
        """decode_access_token lança ExpiredSignatureError → ValueError com mensagem de expirado."""
        with patch(
            "modules.auth.application.use_cases.refresh_token.decode_access_token",
            side_effect=jwt.ExpiredSignatureError,
        ):
            with pytest.raises(ValueError, match="expirado"):
                await self.use_case.execute(RefreshTokenInput(refresh_token="expired.token"))

    async def test_refresh_raises_when_token_is_invalid(self) -> None:
        """decode_access_token lança InvalidTokenError → ValueError com mensagem de inválido."""
        with patch(
            "modules.auth.application.use_cases.refresh_token.decode_access_token",
            side_effect=jwt.InvalidTokenError,
        ):
            with pytest.raises(ValueError, match="inválido"):
                await self.use_case.execute(RefreshTokenInput(refresh_token="garbage.token"))

    async def test_refresh_raises_when_token_type_is_not_refresh(self) -> None:
        """Payload com type='access' passado como refresh → ValueError."""
        user = UserFactory.make()
        payload = _make_valid_payload(user.id, token_type="access")  # tipo errado

        with patch(
            "modules.auth.application.use_cases.refresh_token.decode_access_token",
            return_value=payload,
        ):
            with pytest.raises(ValueError, match="não é um token de refresh"):
                await self.use_case.execute(
                    RefreshTokenInput(refresh_token="access.token.used.as.refresh")
                )

    async def test_refresh_raises_when_token_is_blacklisted(self) -> None:
        """JTI presente na blacklist (token revogado) → ValueError."""
        user = UserFactory.make()
        payload = _make_valid_payload(user.id, token_type="refresh")

        with (
            patch(
                "modules.auth.application.use_cases.refresh_token.decode_access_token",
                return_value=payload,
            ),
            patch(
                "modules.auth.application.use_cases.refresh_token.is_token_blacklisted",
                new_callable=AsyncMock,
                return_value=True,  # token revogado
            ),
        ):
            with pytest.raises(ValueError, match="revogado"):
                await self.use_case.execute(RefreshTokenInput(refresh_token="blacklisted.token"))

    async def test_refresh_raises_when_user_not_found(self) -> None:
        """Token válido mas user_id não existe no repositório → ValueError."""
        unknown_user_id = uuid.uuid4()
        payload = _make_valid_payload(unknown_user_id, token_type="refresh")

        with (
            patch(
                "modules.auth.application.use_cases.refresh_token.decode_access_token",
                return_value=payload,
            ),
            patch(
                "modules.auth.application.use_cases.refresh_token.is_token_blacklisted",
                new_callable=AsyncMock,
                return_value=False,
            ),
        ):
            # repo está vazio — find_by_id retorna None
            with pytest.raises(ValueError, match="não encontrado"):
                await self.use_case.execute(
                    RefreshTokenInput(refresh_token="valid.token.unknown.user")
                )

    async def test_refresh_rotates_old_token_and_preserves_tenant_scope(self) -> None:
        """RTR: invalida refresh token anterior no Redis e preserva tenant_id e role."""
        user = UserFactory.make()
        self.repo.seed(user)
        tenant_id = uuid.uuid4()
        now_ts = int(datetime.now(timezone.utc).timestamp())
        payload = {
            "jti": str(uuid.uuid4()),
            "sub": str(user.id),
            "tenant_id": str(tenant_id),
            "role": "admin",
            "type": "refresh",
            "exp": now_ts + 3600,
        }

        with (
            patch(
                "modules.auth.application.use_cases.refresh_token.decode_access_token",
                return_value=payload,
            ),
            patch(
                "modules.auth.application.use_cases.refresh_token.is_token_blacklisted",
                new_callable=AsyncMock,
                return_value=False,
            ),
            patch(
                "modules.auth.application.use_cases.refresh_token.add_token_to_blacklist",
                new_callable=AsyncMock,
            ) as mock_blacklist,
            patch(
                "modules.auth.application.use_cases.refresh_token.create_access_token",
                return_value="new.access.token",
            ) as mock_create_access,
            patch(
                "modules.auth.application.use_cases.refresh_token.create_refresh_token",
                return_value="new.refresh.token",
            ) as mock_create_refresh,
        ):
            result = await self.use_case.execute(
                RefreshTokenInput(refresh_token="old.refresh.token")
            )

        assert result.access_token == "new.access.token"
        assert result.refresh_token == "new.refresh.token"
        mock_blacklist.assert_called_once()
        assert mock_blacklist.call_args.kwargs["jti"] == payload["jti"]
        mock_create_access.assert_called_once_with(
            user_id=user.id,
            tenant_id=tenant_id,
            role="admin",
        )
        mock_create_refresh.assert_called_once_with(
            user_id=user.id,
            tenant_id=tenant_id,
            role="admin",
        )

    async def test_refresh_detects_reuse_and_revokes_user_sessions(self) -> None:
        """Detecção de reúso: token já revogado apresentado aciona revoke_user_sessions."""
        user = UserFactory.make()
        payload = _make_valid_payload(user.id, token_type="refresh")

        with (
            patch(
                "modules.auth.application.use_cases.refresh_token.decode_access_token",
                return_value=payload,
            ),
            patch(
                "modules.auth.application.use_cases.refresh_token.is_token_blacklisted",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "modules.auth.application.use_cases.refresh_token.revoke_user_sessions",
                new_callable=AsyncMock,
            ) as mock_revoke_sessions,
        ):
            with pytest.raises(ValueError, match="revogado"):
                await self.use_case.execute(RefreshTokenInput(refresh_token="reused.token"))

        mock_revoke_sessions.assert_called_once_with(user.id)
