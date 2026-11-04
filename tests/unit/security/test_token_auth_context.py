from typing import cast
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import Table

from infra.database.models.attendance_record import AttendanceRecordModel
from security.blacklist import check_token_and_session_revocation
from security.dependencies.current_user import (
    get_tenant_token_auth_context,
    get_token_auth_context,
)
from security.jwt import create_access_token
from security.password import hash_password_async, verify_password_async
from shared.enums.user_role import UserRole


@pytest.mark.asyncio
class TestCheckTokenAndSessionRevocation:
    async def test_uses_single_mget_when_jti_present(self) -> None:
        user_id = uuid4()
        with patch("security.blacklist.redis_client") as mock_redis:
            mock_redis.mget = AsyncMock(return_value=[None, None])

            is_blacklisted, is_revoked = await check_token_and_session_revocation(
                jti="jti-123",
                user_id=user_id,
                token_iat=1700000000,
            )

            assert is_blacklisted is False
            assert is_revoked is False
            mock_redis.mget.assert_awaited_once_with(
                "blacklist:jti-123",
                f"user_revoked_before:{user_id}",
            )

    async def test_detects_blacklisted_jti_and_revoked_session(self) -> None:
        user_id = uuid4()
        with patch("security.blacklist.redis_client") as mock_redis:
            mock_redis.mget = AsyncMock(return_value=["revoked", "1700000500.0"])

            is_blacklisted, is_revoked = await check_token_and_session_revocation(
                jti="jti-abc",
                user_id=user_id,
                token_iat=1700000000,
            )

            assert is_blacklisted is True
            assert is_revoked is True


@pytest.mark.asyncio
class TestLightTokenAuthContext:
    async def test_get_token_auth_context_builds_context_without_db(self) -> None:
        user_id = uuid4()
        tenant_id = uuid4()
        token = create_access_token(
            user_id=user_id,
            tenant_id=tenant_id,
            role=UserRole.ALUNO.value,
        )
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

        with patch(
            "security.dependencies.current_user.check_token_and_session_revocation",
            new=AsyncMock(return_value=(False, False)),
        ):
            ctx = await get_token_auth_context(credentials=credentials)
            tenant_ctx = await get_tenant_token_auth_context(ctx=ctx)

        assert tenant_ctx.user.id == user_id
        assert tenant_ctx.tenant_id == tenant_id
        assert tenant_ctx.role == UserRole.ALUNO
        assert tenant_ctx.jti is not None

    async def test_get_tenant_token_auth_context_raises_403_when_no_tenant(self) -> None:
        user_id = uuid4()
        token = create_access_token(user_id=user_id)
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

        with patch(
            "security.dependencies.current_user.check_token_and_session_revocation",
            new=AsyncMock(return_value=(False, False)),
        ):
            ctx = await get_token_auth_context(credentials=credentials)
            with pytest.raises(HTTPException) as exc_info:
                await get_tenant_token_auth_context(ctx=ctx)

        assert exc_info.value.status_code == 403
        assert "Nenhuma tenant selecionada" in exc_info.value.detail

    async def test_get_token_auth_context_raises_401_when_blacklisted(self) -> None:
        user_id = uuid4()
        token = create_access_token(user_id=user_id)
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

        with patch(
            "security.dependencies.current_user.check_token_and_session_revocation",
            new=AsyncMock(return_value=(True, False)),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await get_token_auth_context(credentials=credentials)

        assert exc_info.value.status_code == 401
        assert "revogado" in exc_info.value.detail.lower()


def test_attendance_record_model_has_session_device_partial_index() -> None:
    table = cast(Table, AttendanceRecordModel.__table__)
    index_names = {idx.name for idx in table.indexes}
    assert "ix_attendance_records_session_device" in index_names


@pytest.mark.asyncio
class TestAsyncPasswordHashing:
    async def test_hash_and_verify_password_async_via_to_thread(self) -> None:
        hashed = await hash_password_async("SenhaForte@2026")
        assert hashed != "SenhaForte@2026"
        assert await verify_password_async("SenhaForte@2026", hashed) is True
        assert await verify_password_async("SenhaErrada", hashed) is False
