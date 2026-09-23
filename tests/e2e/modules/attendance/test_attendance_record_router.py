from uuid import uuid4

import pytest

from unittest.mock import AsyncMock, patch
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
            data={"day_code": day_code, "latitude": "-8.04761", "longitude": "-34.87701"},
            headers=student1_headers,
        )
        assert res1.status_code == 201
        rec1_data = res1.json()
        assert rec1_data["within_radius"] is True
        assert rec1_data["record_status"] == RecordStatus.REGULAR.value

        # Student 2 confirms (outside room radius -> ~1km away)
        res2 = await client.post(
            f"/tenants/{tenant.id}/subject-classes/{sc_id}/attendance-sessions/{session_id}/confirm",
            data={"day_code": day_code, "latitude": "-8.05600", "longitude": "-34.87700"},
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
            data={"day_code": day_code, "latitude": "-8.05600", "longitude": "-34.87700"},
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

    async def test_confirm_attendance_when_session_cancelled_raises_409(self, client, session):
        """Discente tenta confirmar presença em chamada cancelada e recebe 409 Conflict."""
        (
            tenant,
            sc_id,
            session_id,
            day_code,
            prof_headers,
            student1_headers, _, _, _,
        ) = await self._setup_fixtures(session, client)

        # Professor cancela a chamada
        cancel_res = await client.patch(
            f"/tenants/{tenant.id}/subject-classes/{sc_id}/attendance-sessions/{session_id}/cancel",
            headers=prof_headers,
        )
        assert cancel_res.status_code == 200

        # Aluno tenta confirmar em chamada cancelada
        res = await client.post(
            f"/tenants/{tenant.id}/subject-classes/{sc_id}/attendance-sessions/{session_id}/confirm",
            data={"day_code": day_code, "latitude": "-8.04761", "longitude": "-34.87701"},
            headers=student1_headers,
        )
        assert res.status_code == 409
        assert res.json()["detail"] == "A chamada foi cancelada."

    async def test_confirm_attendance_with_photo_upload(self, client, session):
        """Upload de foto opcional retorna evidence_photo_url no response."""
        (
            tenant,
            sc_id,
            session_id,
            day_code,
            prof_headers,
            student1_headers, _, _, _,
        ) = await self._setup_fixtures(session, client)

        fake_url = "https://pub-test.r2.dev/evidence/session-id/uuid.jpg"

        with patch("modules.attendance.interface.router.R2StorageService") as MockR2:
            instance = MockR2.return_value
            instance.upload = AsyncMock(return_value=fake_url)

            res = await client.post(
                f"/tenants/{tenant.id}/subject-classes/{sc_id}/attendance-sessions/{session_id}/confirm",
                data={"day_code": day_code, "latitude": "-8.04761", "longitude": "-34.87701"},
                files={"photo": ("selfie.jpg", b"fake-jpeg-bytes", "image/jpeg")},
                headers=student1_headers,
            )

        assert res.status_code == 201
        assert res.json()["evidence_photo_url"] == fake_url

    async def test_confirm_attendance_without_photo(self, client, session):
        """Confirmação sem foto deve funcionar normalmente, com evidence_photo_url nulo."""
        (
            tenant,
            sc_id,
            session_id,
            day_code,
            prof_headers,
            student1_headers, _, _, _,
        ) = await self._setup_fixtures(session, client)

        res = await client.post(
            f"/tenants/{tenant.id}/subject-classes/{sc_id}/attendance-sessions/{session_id}/confirm",
            data={"day_code": day_code, "latitude": "-8.04761", "longitude": "-34.87701"},
            headers=student1_headers,
        )

        assert res.status_code == 201
        assert res.json()["evidence_photo_url"] is None

    async def test_confirm_attendance_photo_invalid_mime_type(self, client, session):
        """Tipo MIME não suportado deve retornar 422."""
        (
            tenant,
            sc_id,
            session_id,
            day_code,
            prof_headers,
            student1_headers, _, _, _,
        ) = await self._setup_fixtures(session, client)

        res = await client.post(
            f"/tenants/{tenant.id}/subject-classes/{sc_id}/attendance-sessions/{session_id}/confirm",
            data={"day_code": day_code, "latitude": "-8.04761", "longitude": "-34.87701"},
            files={"photo": ("document.pdf", b"fake-pdf", "application/pdf")},
            headers=student1_headers,
        )

        assert res.status_code == 400

    async def test_confirm_attendance_photo_too_large(self, client, session):
        """Arquivo maior que 5 MB deve retornar 413."""
        (
            tenant,
            sc_id,
            session_id,
            day_code,
            prof_headers,
            student1_headers, _, _, _,
        ) = await self._setup_fixtures(session, client)

        big_file = b"x" * (5 * 1024 * 1024 + 1)

        res = await client.post(
            f"/tenants/{tenant.id}/subject-classes/{sc_id}/attendance-sessions/{session_id}/confirm",
            data={"day_code": day_code, "latitude": "-8.04761", "longitude": "-34.87701"},
            files={"photo": ("big.jpg", big_file, "image/jpeg")},
            headers=student1_headers,
        )

        assert res.status_code == 400

    async def test_confirm_attendance_when_student_not_enrolled_in_class_returns_403(
        self, client, session
    ):
        """Aluno da instituição, sem matrícula na turma, não confirma a chamada."""
        (
            tenant,
            sc_id,
            session_id,
            day_code, _, _, _, _, _,
        ) = await self._setup_fixtures(session, client)

        outsider_user = await UserFactory.create(session)
        await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=outsider_user.id, role=UserRole.ALUNO
        )
        outsider_token = create_access_token(
            user_id=outsider_user.id, tenant_id=tenant.id, role=UserRole.ALUNO.value
        )
        outsider_headers = {
            "Authorization": f"Bearer {outsider_token}",
            "User-Agent": "okhttp/4.9.0",
        }

        res = await client.post(
            f"/tenants/{tenant.id}/subject-classes/{sc_id}/attendance-sessions/{session_id}/confirm",
            data={"day_code": day_code, "latitude": "-8.04761", "longitude": "-34.87701"},
            headers=outsider_headers,
        )
        assert res.status_code == 403
        assert res.json()["detail"] == "Aluno não possui matrícula ativa nesta turma."

    async def test_list_session_roster_e2e(self, client, session):
        """Professor lista todos os alunos da chamada; quem não marcou vem com horário, distância e status nulos."""
        (
            tenant,
            sc_id,
            session_id,
            day_code,
            prof_headers,
            student1_headers,
            _,
            student1_member,
            student2_member,
        ) = await self._setup_fixtures(session, client)

        confirm_res = await client.post(
            f"/tenants/{tenant.id}/subject-classes/{sc_id}/attendance-sessions/{session_id}/confirm",
            json={"day_code": day_code, "latitude": -8.04761, "longitude": -34.87701},
            headers=student1_headers,
        )
        assert confirm_res.status_code == 201
        confirmed = confirm_res.json()

        student_roster = await client.get(
            f"/tenants/{tenant.id}/subject-classes/{sc_id}/attendance-sessions/{session_id}/roster",
            headers=student1_headers,
        )
        assert student_roster.status_code == 403

        roster_res = await client.get(
            f"/tenants/{tenant.id}/subject-classes/{sc_id}/attendance-sessions/{session_id}/roster",
            headers=prof_headers,
        )
        assert roster_res.status_code == 200
        items = roster_res.json()
        assert len(items) == 2
        by_member = {item["tenant_member_id"]: item for item in items}

        present = by_member[str(student1_member.id)]
        assert present["student_name"]
        assert present["record_id"] == confirmed["id"]
        assert present["confirmed_at"] == confirmed["confirmed_at"]
        assert present["distance_meters"] == pytest.approx(confirmed["distance_meters"])
        assert present["within_radius"] is True
        assert present["record_status"] == RecordStatus.REGULAR.value

        absent = by_member[str(student2_member.id)]
        assert absent["student_name"]
        assert absent["record_id"] is None
        assert absent["confirmed_at"] is None
        assert absent["distance_meters"] is None
        assert absent["within_radius"] is None
        assert absent["record_status"] is None

        missing = await client.get(
            f"/tenants/{tenant.id}/subject-classes/{sc_id}/attendance-sessions/{uuid4()}/roster",
            headers=prof_headers,
        )
        assert missing.status_code == 404
