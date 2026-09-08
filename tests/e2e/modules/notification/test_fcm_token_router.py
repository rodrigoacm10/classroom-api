import pytest

from security.jwt import create_access_token
from shared.enums.user_role import UserRole
from tests.factories.tenant_factory import TenantFactory
from tests.factories.user_factory import UserFactory


@pytest.mark.asyncio
class TestFCMTokenRouter:
    """
    Suíte de Testes (E2E): FCMTokenRouter
    Valida a integração ponta a ponta da API HTTP para cadastro, atualização e desvinculação de tokens FCM.
    """

    async def _setup_fixtures(self, session):
        student_user = await UserFactory.create(session)
        tenant = await TenantFactory.create(session)
        await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=student_user.id, role=UserRole.ALUNO
        )

        student_token = create_access_token(
            user_id=student_user.id, tenant_id=tenant.id, role=UserRole.ALUNO.value
        )
        student_headers = {"Authorization": f"Bearer {student_token}"}

        return tenant, student_user, student_headers

    async def test_register_fcm_token_e2e_success(self, client, session):
        """Deve cadastrar um novo token FCM via POST /tenants/{tenant_id}/fcm-tokens retornando status 200 OK."""
        tenant, _, student_headers = await self._setup_fixtures(session)

        res = await client.post(
            f"/tenants/{tenant.id}/fcm-tokens",
            json={
                "device_id": "device-uuid-abc123",
                "fcm_token": "fcm-token-xyz789",
                "platform": "android",
                "app_version": "1.2.3",
            },
            headers=student_headers,
        )

        assert res.status_code == 200
        data = res.json()
        assert data["device_id"] == "device-uuid-abc123"
        assert data["platform"] == "android"
        assert "updated_at" in data

    async def test_register_fcm_token_upsert_e2e(self, client, session):
        """Deve atualizar o token FCM de um dispositivo já existente sem criar registros duplicados via POST /tenants/{tenant_id}/fcm-tokens."""
        tenant, _, student_headers = await self._setup_fixtures(session)

        # Primeiro envio
        res1 = await client.post(
            f"/tenants/{tenant.id}/fcm-tokens",
            json={
                "device_id": "device-uuid-abc123",
                "fcm_token": "token-old",
                "platform": "android",
            },
            headers=student_headers,
        )
        assert res1.status_code == 200

        # Segundo envio com novo fcm_token
        res2 = await client.post(
            f"/tenants/{tenant.id}/fcm-tokens",
            json={
                "device_id": "device-uuid-abc123",
                "fcm_token": "token-new",
                "platform": "android",
            },
            headers=student_headers,
        )
        assert res2.status_code == 200
        assert res2.json()["device_id"] == "device-uuid-abc123"

    async def test_remove_fcm_token_e2e_success(self, client, session):
        """Deve remover o token FCM do dispositivo ao fazer logout via DELETE /tenants/{tenant_id}/fcm-tokens/{device_id} retornando 204 No Content."""
        tenant, _, student_headers = await self._setup_fixtures(session)

        # Registra primeiro
        reg_res = await client.post(
            f"/tenants/{tenant.id}/fcm-tokens",
            json={
                "device_id": "device-to-remove",
                "fcm_token": "fcm-token-temp",
                "platform": "ios",
            },
            headers=student_headers,
        )
        assert reg_res.status_code == 200

        # Remove
        del_res = await client.delete(
            f"/tenants/{tenant.id}/fcm-tokens/device-to-remove",
            headers=student_headers,
        )
        assert del_res.status_code == 204

    async def test_remove_fcm_token_e2e_not_found(self, client, session):
        """Deve retornar 404 Not Found ao tentar deletar o token de um dispositivo inexistente via DELETE /tenants/{tenant_id}/fcm-tokens/{device_id}."""
        tenant, _, student_headers = await self._setup_fixtures(session)

        del_res = await client.delete(
            f"/tenants/{tenant.id}/fcm-tokens/non-existent-device",
            headers=student_headers,
        )
        assert del_res.status_code == 404

    async def test_register_fcm_token_multi_device_e2e(self, client, session):
        """Deve suportar logins simultâneos em múltiplos dispositivos (celular + tablet) permitindo logout independente em cada aparelho."""
        tenant, student_user, student_headers = await self._setup_fixtures(session)

        # 1. Registrar dispositivo Celular (Android)
        res_mobile = await client.post(
            f"/tenants/{tenant.id}/fcm-tokens",
            json={
                "device_id": "device-mobile-xyz-100",
                "fcm_token": "fcm-token-mobile-aaa",
                "platform": "android",
                "app_version": "2.1.0",
            },
            headers=student_headers,
        )
        assert res_mobile.status_code == 200
        assert res_mobile.json()["device_id"] == "device-mobile-xyz-100"

        # 2. Registrar dispositivo Tablet (iOS)
        res_tablet = await client.post(
            f"/tenants/{tenant.id}/fcm-tokens",
            json={
                "device_id": "device-tablet-xyz-200",
                "fcm_token": "fcm-token-tablet-bbb",
                "platform": "ios",
                "app_version": "2.1.0",
            },
            headers=student_headers,
        )
        assert res_tablet.status_code == 200
        assert res_tablet.json()["device_id"] == "device-tablet-xyz-200"

        # 3. Remover apenas o celular (logout do celular)
        del_mobile = await client.delete(
            f"/tenants/{tenant.id}/fcm-tokens/device-mobile-xyz-100",
            headers=student_headers,
        )
        assert del_mobile.status_code == 204

        # 4. Tentar remover o celular de novo deve dar 404, mas o tablet continua existindo
        del_mobile_again = await client.delete(
            f"/tenants/{tenant.id}/fcm-tokens/device-mobile-xyz-100",
            headers=student_headers,
        )
        assert del_mobile_again.status_code == 404

        # 5. Logout do tablet remove o tablet com sucesso
        del_tablet = await client.delete(
            f"/tenants/{tenant.id}/fcm-tokens/device-tablet-xyz-200",
            headers=student_headers,
        )
        assert del_tablet.status_code == 204
