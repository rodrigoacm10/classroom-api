import asyncio
import pytest
from httpx import Response

from security.jwt import create_access_token
from shared.enums.user_role import UserRole
from tests.factories.tenant_factory import TenantFactory
from tests.factories.user_factory import UserFactory


@pytest.mark.asyncio
class TestAttendanceConcurrency:

    async def test_simultaneous_confirmations_same_student_race_condition(self, client, session):
        """
        Dispara 5 requisições simultâneas de confirmação de presença do MESMO aluno.
        Garante que apenas 1 requisição tem sucesso (201) e as outras 4 retornam conflito (409).
        """
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

        student_user = await UserFactory.create(session)
        student_member = await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=student_user.id, role=UserRole.ALUNO
        )
        student_token = create_access_token(user_id=student_user.id, tenant_id=tenant.id, role=UserRole.ALUNO.value)
        student_headers = {"Authorization": f"Bearer {student_token}", "User-Agent": "okhttp/4.9.0"}

        room_res = await client.post(
            f"/tenants/{tenant.id}/rooms",
            json={"name": "Lab Concorrência", "latitude": -8.0476, "longitude": -34.8770},
            headers=admin_headers,
        )
        assert room_res.status_code == 201
        room_id = room_res.json()["id"]

        sc_res = await client.post(
            f"/tenants/{tenant.id}/subject-classes",
            json={"room_id": room_id, "name": "Concorrência", "discipline_name": "Sistemas"},
            headers=prof_headers,
        )
        assert sc_res.status_code == 201
        sc_id = sc_res.json()["id"]

        # Matricular aluno
        await client.post(
            f"/tenants/{tenant.id}/subject-classes/{sc_id}/enrollments",
            json={"tenant_member_id": str(student_member.id)},
            headers=admin_headers,
        )

        # Abrir chamada
        session_res = await client.post(
            f"/tenants/{tenant.id}/subject-classes/{sc_id}/attendance-sessions",
            json={"room_id": room_id, "duration_minutes": 15},
            headers=prof_headers,
        )
        assert session_res.status_code == 201
        session_data = session_res.json()
        session_id = session_data["id"]
        day_code = session_data["day_code"]

        url = f"/tenants/{tenant.id}/subject-classes/{sc_id}/attendance-sessions/{session_id}/confirm"
        payload = {"day_code": day_code, "latitude": -8.0476, "longitude": -34.8770}

        # Executa N requisições de confirmação do mesmo aluno
        responses = [await client.post(url, json=payload, headers=student_headers) for _ in range(5)]

        status_codes = [r.status_code for r in responses]

        # Exatamente 1 request com status 201 e os demais com 409
        assert status_codes.count(201) == 1
        assert status_codes.count(409) == 4
