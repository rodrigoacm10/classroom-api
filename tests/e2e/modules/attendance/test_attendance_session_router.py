import pytest

from security.jwt import create_access_token
from shared.enums.session_status import SessionStatus
from shared.enums.user_role import UserRole
from tests.factories.tenant_factory import TenantFactory
from tests.factories.user_factory import UserFactory


@pytest.mark.asyncio
class TestAttendanceSessionRouter:

    async def _setup_fixtures(self, session, client):
        admin_user = await UserFactory.create(session)
        tenant = await TenantFactory.create(session)
        admin_member = await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=admin_user.id, role=UserRole.ADMIN
        )

        admin_token = create_access_token(user_id=admin_user.id, tenant_id=tenant.id, role=UserRole.ADMIN.value)
        admin_headers = {"Authorization": f"Bearer {admin_token}"}

        prof_user = await UserFactory.create(session)
        prof_member = await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=prof_user.id, role=UserRole.PROFESSOR
        )
        prof_token = create_access_token(user_id=prof_user.id, tenant_id=tenant.id, role=UserRole.PROFESSOR.value)
        prof_headers = {"Authorization": f"Bearer {prof_token}"}

        room_res = await client.post(
            f"/tenants/{tenant.id}/rooms",
            json={"name": "Lab 101", "latitude": -8.0476, "longitude": -34.8770},
            headers=admin_headers,
        )
        assert room_res.status_code == 201
        room_id = room_res.json()["id"]

        sc_res = await client.post(
            f"/tenants/{tenant.id}/subject-classes",
            json={"room_id": room_id, "name": "POO", "discipline_name": "Programação"},
            headers=prof_headers,
        )
        assert sc_res.status_code == 201
        sc_id = sc_res.json()["id"]

        return tenant, admin_headers, prof_headers, sc_id, room_id, prof_member

    async def test_open_session_endpoint_success(self, client, session):
        """POST /attendance-sessions -> Professor abre chamada (201)."""
        tenant, _, prof_headers, sc_id, room_id, _ = await self._setup_fixtures(session, client)

        res = await client.post(
            f"/tenants/{tenant.id}/subject-classes/{sc_id}/attendance-sessions",
            json={"room_id": room_id, "duration_minutes": 20},
            headers=prof_headers,
        )
        assert res.status_code == 201
        data = res.json()
        assert data["subject_class_id"] == sc_id
        assert data["room_id"] == room_id
        assert len(data["day_code"]) == 6
        assert data["status"] == SessionStatus.OPEN.value

    async def test_open_session_endpoint_conflict_when_already_open(self, client, session):
        """POST /attendance-sessions -> Retorna 409 se já houver uma chamada aberta."""
        tenant, _, prof_headers, sc_id, room_id, _ = await self._setup_fixtures(session, client)

        res1 = await client.post(
            f"/tenants/{tenant.id}/subject-classes/{sc_id}/attendance-sessions",
            json={"room_id": room_id, "duration_minutes": 20},
            headers=prof_headers,
        )
        assert res1.status_code == 201

        res2 = await client.post(
            f"/tenants/{tenant.id}/subject-classes/{sc_id}/attendance-sessions",
            json={"room_id": room_id, "duration_minutes": 20},
            headers=prof_headers,
        )
        assert res2.status_code == 409

    async def test_list_and_get_session_endpoints(self, client, session):
        """GET /attendance-sessions e GET /attendance-sessions/{id} retornam sessões corretamente."""
        tenant, _, prof_headers, sc_id, room_id, _ = await self._setup_fixtures(session, client)

        open_res = await client.post(
            f"/tenants/{tenant.id}/subject-classes/{sc_id}/attendance-sessions",
            json={"room_id": room_id, "duration_minutes": 15},
            headers=prof_headers,
        )
        session_id = open_res.json()["id"]

        # List
        list_res = await client.get(
            f"/tenants/{tenant.id}/subject-classes/{sc_id}/attendance-sessions",
            headers=prof_headers,
        )
        assert list_res.status_code == 200
        assert len(list_res.json()) == 1
        item = list_res.json()[0]
        assert item["id"] == session_id
        assert item["subject_class"]["name"] == "POO"
        assert item["subject_class"]["discipline_name"] == "Programação"
        assert item["room"]["name"] == "Lab 101"

        # Get
        get_res = await client.get(
            f"/tenants/{tenant.id}/subject-classes/{sc_id}/attendance-sessions/{session_id}",
            headers=prof_headers,
        )
        assert get_res.status_code == 200
        get_data = get_res.json()
        assert get_data["id"] == session_id
        assert get_data["subject_class"]["name"] == "POO"
        assert get_data["subject_class"]["discipline_name"] == "Programação"
        assert get_data["room"]["name"] == "Lab 101"

    async def test_close_session_endpoint_success_and_conflict(self, client, session):
        """PATCH /attendance-sessions/{id}/close encerra a chamada e retorna 409 se já estiver fechada."""
        tenant, _, prof_headers, sc_id, room_id, _ = await self._setup_fixtures(session, client)

        open_res = await client.post(
            f"/tenants/{tenant.id}/subject-classes/{sc_id}/attendance-sessions",
            json={"room_id": room_id, "duration_minutes": 15},
            headers=prof_headers,
        )
        session_id = open_res.json()["id"]

        # Close 1
        close1_res = await client.patch(
            f"/tenants/{tenant.id}/subject-classes/{sc_id}/attendance-sessions/{session_id}/close",
            headers=prof_headers,
        )
        assert close1_res.status_code == 200
        assert close1_res.json()["status"] == SessionStatus.CLOSED.value

        # Close 2 (Conflict)
        close2_res = await client.patch(
            f"/tenants/{tenant.id}/subject-classes/{sc_id}/attendance-sessions/{session_id}/close",
            headers=prof_headers,
        )
        assert close2_res.status_code == 409

    async def test_cancel_session_endpoint_success_and_conflict(self, client, session):
        """PATCH /attendance-sessions/{id}/cancel cancela a chamada e retorna 409 se já estiver cancelada."""
        tenant, _, prof_headers, sc_id, room_id, _ = await self._setup_fixtures(session, client)

        open_res = await client.post(
            f"/tenants/{tenant.id}/subject-classes/{sc_id}/attendance-sessions",
            json={"room_id": room_id, "duration_minutes": 15},
            headers=prof_headers,
        )
        session_id = open_res.json()["id"]

        # Cancel 1
        cancel1_res = await client.patch(
            f"/tenants/{tenant.id}/subject-classes/{sc_id}/attendance-sessions/{session_id}/cancel",
            headers=prof_headers,
        )
        assert cancel1_res.status_code == 200
        assert cancel1_res.json()["status"] == SessionStatus.CANCELLED.value

        # Cancel 2 (Conflict)
        cancel2_res = await client.patch(
            f"/tenants/{tenant.id}/subject-classes/{sc_id}/attendance-sessions/{session_id}/cancel",
            headers=prof_headers,
        )
        assert cancel2_res.status_code == 409
