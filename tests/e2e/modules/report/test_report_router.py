from uuid import uuid4

import pytest

from security.jwt import create_access_token
from shared.enums.user_role import UserRole
from tests.factories.tenant_factory import TenantFactory
from tests.factories.user_factory import UserFactory


@pytest.fixture(autouse=True)
def _use_sequential_strategy(monkeypatch):
    """E2E valida o contrato HTTP; paralelismo é coberto pelos testes unitários."""
    from config.settings import settings

    monkeypatch.setattr(settings, "report_strategy", "sequential")


@pytest.mark.asyncio
class TestReportRouter:
    """
    Suíte de Testes E2E: rotas de relatório de frequência.
    ADMIN e PROFESSOR podem gerar; ALUNO recebe 403.
    """


    async def _setup(self, session, client, enroll_students: int = 2):
        admin_user = await UserFactory.create(session)
        tenant = await TenantFactory.create(session)
        await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=admin_user.id, role=UserRole.ADMIN
        )
        admin_token = create_access_token(
            user_id=admin_user.id, tenant_id=tenant.id, role=UserRole.ADMIN.value
        )
        admin_headers = {"Authorization": f"Bearer {admin_token}"}

        prof_user = await UserFactory.create(session)
        await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=prof_user.id, role=UserRole.PROFESSOR
        )
        prof_token = create_access_token(
            user_id=prof_user.id, tenant_id=tenant.id, role=UserRole.PROFESSOR.value
        )
        prof_headers = {"Authorization": f"Bearer {prof_token}"}

        room_res = await client.post(
            "/rooms",
            json={"name": "Lab 101", "latitude": -8.0476, "longitude": -34.8770},
            headers=admin_headers,
        )
        assert room_res.status_code == 201
        room_id = room_res.json()["id"]

        sc_res = await client.post(
            "/subject-classes",
            json={"room_id": room_id, "name": "POO", "discipline_name": "Programação"},
            headers=prof_headers,
        )
        assert sc_res.status_code == 201
        sc_id = sc_res.json()["id"]

        students = []
        for i in range(enroll_students):
            student_user = await UserFactory.create(session, name=f"Aluno {i + 1}")
            student_member = await TenantFactory.create_member(
                session, tenant_id=tenant.id, user_id=student_user.id, role=UserRole.ALUNO
            )
            enroll_res = await client.post(
                f"/subject-classes/{sc_id}/enrollments",
                json={"tenant_member_id": str(student_member.id)},
                headers=admin_headers,
            )
            assert enroll_res.status_code == 201
            student_token = create_access_token(
                user_id=student_user.id, tenant_id=tenant.id, role=UserRole.ALUNO.value
            )
            students.append(
                {
                    "member": student_member,
                    "headers": {
                        "Authorization": f"Bearer {student_token}",
                        "User-Agent": "okhttp/4.9.0",
                    },
                }
            )

        return tenant, admin_headers, prof_headers, sc_id, room_id, students

    async def test_gerar_relatorio_e2e(self, client, session):
        """Deve permitir que o PROFESSOR gere o relatório da turma (200) e consulte o detalhe de um aluno."""
        tenant, _, prof_headers, sc_id, room_id, students = await self._setup(
            session, client
        )
        student1, student2 = students

        open_res = await client.post(
            f"/subject-classes/{sc_id}/attendance-sessions",
            json={"room_id": room_id, "duration_minutes": 20},
            headers=prof_headers,
        )
        assert open_res.status_code == 201
        session_data = open_res.json()

        confirm_res = await client.post(
            f"/subject-classes/{sc_id}/attendance-sessions/{session_data['id']}/confirm",
            json={
                "day_code": session_data["day_code"],
                "latitude": -8.04761,
                "longitude": -34.87701,
            },
            headers=student1["headers"],
        )
        assert confirm_res.status_code == 201

        res = await client.post(
            f"/subject-classes/{sc_id}/reports/frequency",
            headers=prof_headers,
        )
        assert res.status_code == 200
        data = res.json()
        assert data["subject_class_id"] == sc_id
        assert data["total_students"] == 2
        assert data["students_at_risk"] == 1
        assert data["strategy_used"] == "sequential"
        assert data["workers_used"] == 1
        assert "duration_ms" in data
        assert len(data["students"]) == 2

        by_id = {s["tenant_member_id"]: s for s in data["students"]}
        present = by_id[str(student1["member"].id)]
        absent = by_id[str(student2["member"].id)]
        assert present["total_present"] == 1
        assert present["total_absent"] == 0
        assert present["frequency_rate"] == 1.0
        assert present["at_risk"] is False
        assert absent["total_present"] == 0
        assert absent["total_absent"] == 1
        assert absent["frequency_rate"] == 0.0
        assert absent["at_risk"] is True

        detail = await client.get(
            f"/subject-classes/{sc_id}/reports/frequency/{student1['member'].id}",
            headers=prof_headers,
        )
        assert detail.status_code == 200
        assert detail.json()["tenant_member_id"] == str(student1["member"].id)
        assert detail.json()["frequency_rate"] == 1.0

    async def test_gerar_relatorio_sucesso_admin(self, client, session):
        """Deve permitir que o ADMIN gere o relatório da turma (200)."""
        tenant, admin_headers, _, sc_id, _, _ = await self._setup(session, client)

        res = await client.post(
            f"/subject-classes/{sc_id}/reports/frequency",
            headers=admin_headers,
        )
        assert res.status_code == 200
        assert res.json()["total_students"] == 2

    async def test_gerar_relatorio_403_para_aluno(self, client, session):
        """Deve recusar com 403 quando um ALUNO tenta gerar o relatório da turma."""
        tenant, _, _, sc_id, _, students = await self._setup(session, client)

        res = await client.post(
            f"/subject-classes/{sc_id}/reports/frequency",
            headers=students[0]["headers"],
        )
        assert res.status_code == 403

    async def test_get_relatorio_aluno_403_para_aluno(self, client, session):
        """Deve recusar com 403 quando um ALUNO tenta ver o detalhe de frequência de um colega."""
        tenant, _, _, sc_id, _, students = await self._setup(session, client)

        res = await client.get(
            f"/subject-classes/{sc_id}/reports/frequency/{students[1]['member'].id}",
            headers=students[0]["headers"],
        )
        assert res.status_code == 403

    async def test_gerar_relatorio_404_turma_inexistente(self, client, session):
        """Deve retornar 404 quando o PROFESSOR pede relatório de uma turma inexistente."""
        tenant, _, prof_headers, _, _, _ = await self._setup(session, client, enroll_students=0)

        res = await client.post(
            f"/subject-classes/{uuid4()}/reports/frequency",
            headers=prof_headers,
        )
        assert res.status_code == 404

    async def test_get_relatorio_404_aluno_nao_matriculado(self, client, session):
        """Deve retornar 404 no detalhe quando o tenant_member_id não está na turma."""
        tenant, _, prof_headers, sc_id, _, _ = await self._setup(session, client)

        res = await client.get(
            f"/subject-classes/{sc_id}/reports/frequency/{uuid4()}",
            headers=prof_headers,
        )
        assert res.status_code == 404

    async def test_get_relatorio_404_turma_inexistente(self, client, session):
        """Deve retornar 404 no detalhe quando a turma não existe."""
        tenant, _, prof_headers, _, _, students = await self._setup(session, client)

        res = await client.get(
            f"/subject-classes/{uuid4()}/reports/frequency/{students[0]['member'].id}",
            headers=prof_headers,
        )
        assert res.status_code == 404

    async def test_gerar_relatorio_sem_token_nao_autoriza(self, client, session):
        """Deve recusar POST /frequency sem Authorization (401 ou 403 do HTTPBearer)."""
        tenant, _, _, sc_id, _, _ = await self._setup(session, client, enroll_students=0)

        res = await client.post(
            f"/subject-classes/{sc_id}/reports/frequency"
        )
        assert res.status_code in (401, 403)
