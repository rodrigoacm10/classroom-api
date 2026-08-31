import pytest

from security.jwt import create_access_token
from shared.enums.record_status import RecordStatus
from shared.enums.user_role import UserRole
from tests.factories.tenant_factory import TenantFactory
from tests.factories.user_factory import UserFactory


@pytest.mark.asyncio
class TestAttendanceRecordRouter:

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

        student1_user = await UserFactory.create(session)
        student1_member = await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=student1_user.id, role=UserRole.ALUNO
        )
        student1_token = create_access_token(user_id=student1_user.id, tenant_id=tenant.id, role=UserRole.ALUNO.value)
        student1_headers = {"Authorization": f"Bearer {student1_token}", "User-Agent": "okhttp/4.9.0"}

        student2_user = await UserFactory.create(session)
        student2_member = await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=student2_user.id, role=UserRole.ALUNO
        )
        student2_token = create_access_token(user_id=student2_user.id, tenant_id=tenant.id, role=UserRole.ALUNO.value)
        student2_headers = {"Authorization": f"Bearer {student2_token}", "User-Agent": "okhttp/4.9.0"}

        # Room
        room_res = await client.post(
            f"/tenants/{tenant.id}/rooms",
            json={"name": "Lab 101", "latitude": -8.0476, "longitude": -34.8770, "tolerance_radius_meters": 50},
            headers=admin_headers,
        )
        assert room_res.status_code == 201
        room_id = room_res.json()["id"]

        # Subject class
        sc_res = await client.post(
            f"/tenants/{tenant.id}/subject-classes",
            json={"room_id": room_id, "name": "POO", "discipline_name": "Programação"},
            headers=prof_headers,
        )
        assert sc_res.status_code == 201
        sc_id = sc_res.json()["id"]

        # Enroll student 1 and student 2
        await client.post(
            f"/tenants/{tenant.id}/subject-classes/{sc_id}/enrollments",
            json={"tenant_member_id": str(student1_member.id)},
            headers=admin_headers,
        )
        await client.post(
            f"/tenants/{tenant.id}/subject-classes/{sc_id}/enrollments",
            json={"tenant_member_id": str(student2_member.id)},
            headers=admin_headers,
        )

        # Open session
        session_res = await client.post(
            f"/tenants/{tenant.id}/subject-classes/{sc_id}/attendance-sessions",
            json={"room_id": room_id, "duration_minutes": 20},
            headers=prof_headers,
        )
        assert session_res.status_code == 201
        session_data = session_res.json()

        return (
            tenant,
            sc_id,
            session_data["id"],
            session_data["day_code"],
            prof_headers,
            student1_headers,
            student2_headers,
            student1_member,
            student2_member,
        )

    async def test_confirm_and_list_records_e2e(self, client, session):
        """Discente confirma presença e professor lista os registros."""
        (
            tenant,
            sc_id,
            session_id,
            day_code,
            prof_headers,
            student1_headers,
            student2_headers, _, _,
        ) = await self._setup_fixtures(session, client)

        # Student 1 confirms (inside room radius)
        res1 = await client.post(
            f"/tenants/{tenant.id}/subject-classes/{sc_id}/attendance-sessions/{session_id}/confirm",
            json={"day_code": day_code, "latitude": -8.04761, "longitude": -34.87701},
            headers=student1_headers,
        )
        assert res1.status_code == 201
        rec1_data = res1.json()
        assert rec1_data["within_radius"] is True
        assert rec1_data["record_status"] == RecordStatus.REGULAR.value

        # Student 2 confirms (outside room radius -> ~1km away)
        res2 = await client.post(
            f"/tenants/{tenant.id}/subject-classes/{sc_id}/attendance-sessions/{session_id}/confirm",
            json={"day_code": day_code, "latitude": -8.05600, "longitude": -34.87700},
            headers=student2_headers,
        )
        assert res2.status_code == 201
        rec2_data = res2.json()
        assert rec2_data["within_radius"] is False
        assert rec2_data["record_status"] == RecordStatus.IRREGULAR.value
        assert "outside_radius" in rec2_data["irregularity_flags"]

        # List all records
        list_res = await client.get(
            f"/tenants/{tenant.id}/subject-classes/{sc_id}/attendance-sessions/{session_id}/records",
            headers=prof_headers,
        )
        assert list_res.status_code == 200
        assert len(list_res.json()) == 2

        # List irregular records only
        list_irreg = await client.get(
            f"/tenants/{tenant.id}/subject-classes/{sc_id}/attendance-sessions/{session_id}/records?record_status=irregular",
            headers=prof_headers,
        )
        assert list_irreg.status_code == 200
        assert len(list_irreg.json()) == 1
        assert list_irreg.json()[0]["id"] == rec2_data["id"]

    async def test_review_record_flow_e2e(self, client, session):
        """Professor revisa um registro irregular aprovando-o ou rejeitando-o."""
        (
            tenant,
            sc_id,
            session_id,
            day_code,
            prof_headers,
            _,
            student2_headers, _, _,
        ) = await self._setup_fixtures(session, client)

        # Student 2 confirms outside radius -> irregular
        res2 = await client.post(
            f"/tenants/{tenant.id}/subject-classes/{sc_id}/attendance-sessions/{session_id}/confirm",
            json={"day_code": day_code, "latitude": -8.05600, "longitude": -34.87700},
            headers=student2_headers,
        )
        assert res2.status_code == 201
        record_id = res2.json()["id"]

        # Review - Approve
        rev_res = await client.patch(
            f"/tenants/{tenant.id}/subject-classes/{sc_id}/attendance-sessions/{session_id}/records/{record_id}/review",
            json={"decision": "approved", "note": "Aluno estava na secretaria"},
            headers=prof_headers,
        )
        assert rev_res.status_code == 200
        rev_data = rev_res.json()
        assert rev_data["record_status"] == RecordStatus.APPROVED.value
        assert rev_data["review_note"] == "Aluno estava na secretaria"
        assert rev_data["reviewed_by"] is not None
        assert rev_data["reviewed_at"] is not None
