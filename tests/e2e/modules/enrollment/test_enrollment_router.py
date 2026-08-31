import pytest

from security.jwt import create_access_token
from shared.enums.enrollment_status import EnrollmentStatus
from shared.enums.user_role import UserRole
from tests.factories.tenant_factory import TenantFactory
from tests.factories.user_factory import UserFactory


@pytest.mark.asyncio
class TestEnrollmentRouterEndpoints:
    """Testes E2E para as rotas do módulo Enrollment."""

    async def _setup_tenant_class(self, session, client):
        admin_user = await UserFactory.create(session)
        tenant = await TenantFactory.create(session)
        admin_member = await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=admin_user.id, role=UserRole.ADMIN
        )

        token = create_access_token(
            user_id=admin_user.id, tenant_id=tenant.id, role=UserRole.ADMIN.value
        )
        headers = {"Authorization": f"Bearer {token}"}

        room_payload = {"name": "Sala 101", "latitude": -8.0, "longitude": -34.0}
        room_res = await client.post(
            f"/tenants/{tenant.id}/rooms", json=room_payload, headers=headers
        )
        assert room_res.status_code == 201
        room_id = room_res.json()["id"]

        sc_payload = {
            "room_id": room_id,
            "name": "Turma A",
            "discipline_name": "Cálculo 1",
        }
        sc_res = await client.post(
            f"/tenants/{tenant.id}/subject-classes", json=sc_payload, headers=headers
        )
        assert sc_res.status_code == 201
        sc_id = sc_res.json()["id"]

        return tenant, admin_user, admin_member, headers, sc_id

    async def test_enroll_student_success_admin(self, client, session):
        """POST /enrollments -> ADMIN pode matricular um ALUNO na turma (201)."""
        tenant, admin_user, admin_member, headers, sc_id = await self._setup_tenant_class(
            session, client
        )

        student_user = await UserFactory.create(session)
        student_member = await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=student_user.id, role=UserRole.ALUNO
        )

        res = await client.post(
            f"/tenants/{tenant.id}/subject-classes/{sc_id}/enrollments",
            json={"tenant_member_id": str(student_member.id)},
            headers=headers,
        )
        assert res.status_code == 201
        data = res.json()
        assert data["subject_class_id"] == sc_id
        assert data["tenant_member_id"] == str(student_member.id)
        assert data["status"] == EnrollmentStatus.ACTIVE.value

    async def test_enroll_student_success_professor(self, client, session):
        """POST /enrollments -> PROFESSOR pode matricular um ALUNO na turma (201)."""
        tenant, _, _, _, sc_id = await self._setup_tenant_class(session, client)

        prof_user = await UserFactory.create(session)
        await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=prof_user.id, role=UserRole.PROFESSOR
        )
        prof_token = create_access_token(
            user_id=prof_user.id, tenant_id=tenant.id, role=UserRole.PROFESSOR.value
        )
        prof_headers = {"Authorization": f"Bearer {prof_token}"}

        student_user = await UserFactory.create(session)
        student_member = await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=student_user.id, role=UserRole.ALUNO
        )

        res = await client.post(
            f"/tenants/{tenant.id}/subject-classes/{sc_id}/enrollments",
            json={"tenant_member_id": str(student_member.id)},
            headers=prof_headers,
        )
        assert res.status_code == 201
        assert res.json()["status"] == EnrollmentStatus.ACTIVE.value

    async def test_enroll_student_forbidden_for_aluno(self, client, session):
        """POST /enrollments -> ALUNO tentando matricular deve receber 403 Forbidden."""
        tenant, _, _, _, sc_id = await self._setup_tenant_class(session, client)

        student1_user = await UserFactory.create(session)
        student1_member = await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=student1_user.id, role=UserRole.ALUNO
        )
        token = create_access_token(
            user_id=student1_user.id, tenant_id=tenant.id, role=UserRole.ALUNO.value
        )
        student_headers = {"Authorization": f"Bearer {token}"}

        res = await client.post(
            f"/tenants/{tenant.id}/subject-classes/{sc_id}/enrollments",
            json={"tenant_member_id": str(student1_member.id)},
            headers=student_headers,
        )
        assert res.status_code == 403

    async def test_enroll_member_with_professor_role_fails(self, client, session):
        """POST /enrollments -> Matricular membro com role PROFESSOR deve retornar 400."""
        tenant, _, _, headers, sc_id = await self._setup_tenant_class(session, client)

        prof2_user = await UserFactory.create(session)
        prof2_member = await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=prof2_user.id, role=UserRole.PROFESSOR
        )

        res = await client.post(
            f"/tenants/{tenant.id}/subject-classes/{sc_id}/enrollments",
            json={"tenant_member_id": str(prof2_member.id)},
            headers=headers,
        )
        assert res.status_code == 400

    async def test_enroll_duplicate_active_student_fails(self, client, session):
        """POST /enrollments -> Matricular o mesmo aluno duas vezes deve retornar 409 Conflict."""
        tenant, _, _, headers, sc_id = await self._setup_tenant_class(session, client)

        student_user = await UserFactory.create(session)
        student_member = await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=student_user.id, role=UserRole.ALUNO
        )

        res1 = await client.post(
            f"/tenants/{tenant.id}/subject-classes/{sc_id}/enrollments",
            json={"tenant_member_id": str(student_member.id)},
            headers=headers,
        )
        assert res1.status_code == 201

        res2 = await client.post(
            f"/tenants/{tenant.id}/subject-classes/{sc_id}/enrollments",
            json={"tenant_member_id": str(student_member.id)},
            headers=headers,
        )
        assert res2.status_code == 409

    async def test_list_enrollments(self, client, session):
        """GET /enrollments -> Deve listar matriculados e permitir filtros."""
        tenant, _, _, headers, sc_id = await self._setup_tenant_class(session, client)

        st1_user = await UserFactory.create(session)
        st1_member = await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=st1_user.id, role=UserRole.ALUNO
        )

        st2_user = await UserFactory.create(session)
        st2_member = await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=st2_user.id, role=UserRole.ALUNO
        )

        # Enroll both
        await client.post(
            f"/tenants/{tenant.id}/subject-classes/{sc_id}/enrollments",
            json={"tenant_member_id": str(st1_member.id)},
            headers=headers,
        )
        e2_res = await client.post(
            f"/tenants/{tenant.id}/subject-classes/{sc_id}/enrollments",
            json={"tenant_member_id": str(st2_member.id)},
            headers=headers,
        )
        e2_id = e2_res.json()["id"]

        # Drop st2
        await client.patch(
            f"/tenants/{tenant.id}/subject-classes/{sc_id}/enrollments/{e2_id}",
            headers=headers,
        )

        # GET without filter -> includes both (active & dropped)
        res_all = await client.get(
            f"/tenants/{tenant.id}/subject-classes/{sc_id}/enrollments",
            headers=headers,
        )
        assert res_all.status_code == 200
        assert len(res_all.json()) == 2

        # GET ?status=active -> includes only st1
        res_active = await client.get(
            f"/tenants/{tenant.id}/subject-classes/{sc_id}/enrollments?status=active",
            headers=headers,
        )
        assert res_active.status_code == 200
        data_active = res_active.json()
        assert len(data_active) == 1
        assert data_active[0]["tenant_member_id"] == str(st1_member.id)

    async def test_drop_and_reactivate_enrollment(self, client, session):
        """PATCH /enrollments/{id} -> Cancela (status=dropped). POST novamente reativa (201)."""
        tenant, _, _, headers, sc_id = await self._setup_tenant_class(session, client)

        st_user = await UserFactory.create(session)
        st_member = await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=st_user.id, role=UserRole.ALUNO
        )

        res1 = await client.post(
            f"/tenants/{tenant.id}/subject-classes/{sc_id}/enrollments",
            json={"tenant_member_id": str(st_member.id)},
            headers=headers,
        )
        enrollment_id = res1.json()["id"]

        # Drop
        res_drop = await client.patch(
            f"/tenants/{tenant.id}/subject-classes/{sc_id}/enrollments/{enrollment_id}",
            headers=headers,
        )
        assert res_drop.status_code == 204

        # Reactivate via POST
        res_reactivate = await client.post(
            f"/tenants/{tenant.id}/subject-classes/{sc_id}/enrollments",
            json={"tenant_member_id": str(st_member.id)},
            headers=headers,
        )
        assert res_reactivate.status_code == 201
        assert res_reactivate.json()["id"] == enrollment_id
        assert res_reactivate.json()["status"] == EnrollmentStatus.ACTIVE.value

    async def test_delete_and_recreate_enrollment(self, client, session):
        """DELETE /enrollments/{id} -> Soft delete (204). POST novamente cria novo registro."""
        tenant, _, _, headers, sc_id = await self._setup_tenant_class(session, client)

        st_user = await UserFactory.create(session)
        st_member = await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=st_user.id, role=UserRole.ALUNO
        )

        res1 = await client.post(
            f"/tenants/{tenant.id}/subject-classes/{sc_id}/enrollments",
            json={"tenant_member_id": str(st_member.id)},
            headers=headers,
        )
        old_enrollment_id = res1.json()["id"]

        # Soft delete
        res_del = await client.delete(
            f"/tenants/{tenant.id}/subject-classes/{sc_id}/enrollments/{old_enrollment_id}",
            headers=headers,
        )
        assert res_del.status_code == 204

        # Verify not in normal list
        res_list = await client.get(
            f"/tenants/{tenant.id}/subject-classes/{sc_id}/enrollments",
            headers=headers,
        )
        assert len(res_list.json()) == 0

        # Verify present with include_deleted=true
        res_deleted_list = await client.get(
            f"/tenants/{tenant.id}/subject-classes/{sc_id}/enrollments?include_deleted=true",
            headers=headers,
        )
        assert len(res_deleted_list.json()) == 1

        # Re-enroll creates new record
        res_re_enroll = await client.post(
            f"/tenants/{tenant.id}/subject-classes/{sc_id}/enrollments",
            json={"tenant_member_id": str(st_member.id)},
            headers=headers,
        )
        assert res_re_enroll.status_code == 201
        new_id = res_re_enroll.json()["id"]
        assert new_id != old_enrollment_id

    async def test_member_role_change_drops_enrollments_e2e(self, client, session):
        """Mudar role de ALUNO para PROFESSOR via PATCH /tenants/{id}/members/{user_id}/role altera matrículas ativas para DROPPED."""
        tenant, admin_user, _, headers, sc_id = await self._setup_tenant_class(session, client)

        st_user = await UserFactory.create(session)
        st_member = await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=st_user.id, role=UserRole.ALUNO
        )

        await client.post(
            f"/tenants/{tenant.id}/subject-classes/{sc_id}/enrollments",
            json={"tenant_member_id": str(st_member.id)},
            headers=headers,
        )

        # Update role of st_user to PROFESSOR
        res_role = await client.patch(
            f"/tenants/{tenant.id}/members/{st_user.id}/role",
            json={"role": UserRole.PROFESSOR.value},
            headers=headers,
        )
        assert res_role.status_code == 200
        assert res_role.json()["role"] == UserRole.PROFESSOR.value

        # Check list of active enrollments -> empty
        res_active = await client.get(
            f"/tenants/{tenant.id}/subject-classes/{sc_id}/enrollments?status=active",
            headers=headers,
        )
        assert len(res_active.json()) == 0

        # Check list of all enrollments -> contains dropped enrollment
        res_all = await client.get(
            f"/tenants/{tenant.id}/subject-classes/{sc_id}/enrollments",
            headers=headers,
        )
        assert len(res_all.json()) == 1
        assert res_all.json()[0]["status"] == EnrollmentStatus.DROPPED.value

    async def test_drop_and_delete_enrollment_forbidden_for_professor_and_aluno(self, client, session):
        """PATCH e DELETE /enrollments/{id} por PROFESSOR ou ALUNO deve retornar 403 Forbidden."""
        tenant, _, _, admin_headers, sc_id = await self._setup_tenant_class(session, client)

        st_user = await UserFactory.create(session)
        st_member = await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=st_user.id, role=UserRole.ALUNO
        )

        res_enroll = await client.post(
            f"/tenants/{tenant.id}/subject-classes/{sc_id}/enrollments",
            json={"tenant_member_id": str(st_member.id)},
            headers=admin_headers,
        )
        enrollment_id = res_enroll.json()["id"]

        # Setup Professor headers
        prof_user = await UserFactory.create(session)
        await TenantFactory.create_member(session, tenant_id=tenant.id, user_id=prof_user.id, role=UserRole.PROFESSOR)
        prof_token = create_access_token(user_id=prof_user.id, tenant_id=tenant.id, role=UserRole.PROFESSOR.value)
        prof_headers = {"Authorization": f"Bearer {prof_token}"}

        # Setup Aluno headers
        aluno_token = create_access_token(user_id=st_user.id, tenant_id=tenant.id, role=UserRole.ALUNO.value)
        aluno_headers = {"Authorization": f"Bearer {aluno_token}"}

        # Professor Tenta PATCH -> 403
        res_patch_prof = await client.patch(
            f"/tenants/{tenant.id}/subject-classes/{sc_id}/enrollments/{enrollment_id}",
            headers=prof_headers,
        )
        assert res_patch_prof.status_code == 403

        # Professor Tenta DELETE -> 403
        res_del_prof = await client.delete(
            f"/tenants/{tenant.id}/subject-classes/{sc_id}/enrollments/{enrollment_id}",
            headers=prof_headers,
        )
        assert res_del_prof.status_code == 403

        # Aluno Tenta PATCH -> 403
        res_patch_aluno = await client.patch(
            f"/tenants/{tenant.id}/subject-classes/{sc_id}/enrollments/{enrollment_id}",
            headers=aluno_headers,
        )
        assert res_patch_aluno.status_code == 403

        # Aluno Tenta DELETE -> 403
        res_del_aluno = await client.delete(
            f"/tenants/{tenant.id}/subject-classes/{sc_id}/enrollments/{enrollment_id}",
            headers=aluno_headers,
        )
        assert res_del_aluno.status_code == 403

    async def test_get_enrollment_by_id_endpoint(self, client, session):
        """GET /enrollments/{id} -> Deve retornar os detalhes de uma matrícula (200)."""
        tenant, _, _, headers, sc_id = await self._setup_tenant_class(session, client)

        st_user = await UserFactory.create(session)
        st_member = await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=st_user.id, role=UserRole.ALUNO
        )

        res_create = await client.post(
            f"/tenants/{tenant.id}/subject-classes/{sc_id}/enrollments",
            json={"tenant_member_id": str(st_member.id)},
            headers=headers,
        )
        enrollment_id = res_create.json()["id"]

        res_get = await client.get(
            f"/tenants/{tenant.id}/subject-classes/{sc_id}/enrollments/{enrollment_id}",
            headers=headers,
        )
        assert res_get.status_code == 200
        assert res_get.json()["id"] == enrollment_id
        assert res_get.json()["tenant_member_id"] == str(st_member.id)

    async def test_list_enrollments_by_member_endpoint(self, client, session):
        """GET /tenants/{id}/members/{member_id}/enrollments -> Deve retornar as turmas em que o aluno está matriculado."""
        tenant, _, _, headers, sc_id = await self._setup_tenant_class(session, client)

        st_user = await UserFactory.create(session)
        st_member = await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=st_user.id, role=UserRole.ALUNO
        )

        await client.post(
            f"/tenants/{tenant.id}/subject-classes/{sc_id}/enrollments",
            json={"tenant_member_id": str(st_member.id)},
            headers=headers,
        )

        res_member_enrollments = await client.get(
            f"/tenants/{tenant.id}/members/{st_member.id}/enrollments",
            headers=headers,
        )
        assert res_member_enrollments.status_code == 200
        data = res_member_enrollments.json()
        assert len(data) == 1
        assert data[0]["subject_class_id"] == sc_id


