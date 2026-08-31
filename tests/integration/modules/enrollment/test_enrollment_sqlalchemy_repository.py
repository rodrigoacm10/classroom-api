from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from modules.enrollment.domain.entities.enrollment import Enrollment
from modules.enrollment.infra.repositories.enrollment_sqlalchemy_repository import (
    EnrollmentSQLAlchemyRepository,
)
from modules.subject_class.domain.entities.subject_class import SubjectClass
from modules.subject_class.infra.repositories.subject_class_sqlalchemy_repository import (
    SubjectClassSQLAlchemyRepository,
)
from shared.enums.drop_reason import DropReason
from shared.enums.enrollment_status import EnrollmentStatus
from shared.enums.user_role import UserRole
from tests.factories.tenant_factory import TenantFactory
from tests.factories.user_factory import UserFactory


@pytest.mark.asyncio
class TestEnrollmentSQLAlchemyRepository:

    async def test_save_and_find_by_id(self, session):
        """Deve persistir uma matrícula no banco de dados e recuperá-la por ID."""
        user = await UserFactory.create(session)
        tenant = await TenantFactory.create(session)
        member = await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=user.id, role=UserRole.ALUNO
        )

        sc_repo = SubjectClassSQLAlchemyRepository(session)
        sc = await sc_repo.save(
            SubjectClass(tenant_id=tenant.id, name="Turma A", discipline_name="Math")
        )

        repo = EnrollmentSQLAlchemyRepository(session)
        enrollment = Enrollment(subject_class_id=sc.id, tenant_member_id=member.id)

        saved = await repo.save(enrollment)
        assert saved.id is not None
        assert saved.subject_class_id == sc.id
        assert saved.tenant_member_id == member.id
        assert saved.status == EnrollmentStatus.ACTIVE
        assert saved.deleted is False

        found = await repo.find_by_id(saved.id)
        assert found is not None
        assert found.id == saved.id

    async def test_find_by_class_and_member(self, session):
        """Deve encontrar a matrícula ativa por turma e membro."""
        user = await UserFactory.create(session)
        tenant = await TenantFactory.create(session)
        member = await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=user.id, role=UserRole.ALUNO
        )

        sc_repo = SubjectClassSQLAlchemyRepository(session)
        sc = await sc_repo.save(
            SubjectClass(tenant_id=tenant.id, name="Turma B", discipline_name="Physics")
        )

        repo = EnrollmentSQLAlchemyRepository(session)
        saved = await repo.save(Enrollment(subject_class_id=sc.id, tenant_member_id=member.id))

        found = await repo.find_by_class_and_member(sc.id, member.id)
        assert found is not None
        assert found.id == saved.id

    async def test_list_by_subject_class_with_status_and_deleted_filters(self, session):
        """Deve listar matrículas por turma filtrando por status e deleted."""
        user1 = await UserFactory.create(session)
        user2 = await UserFactory.create(session)
        user3 = await UserFactory.create(session)

        tenant = await TenantFactory.create(session)
        m1 = await TenantFactory.create_member(session, tenant_id=tenant.id, user_id=user1.id, role=UserRole.ALUNO)
        m2 = await TenantFactory.create_member(session, tenant_id=tenant.id, user_id=user2.id, role=UserRole.ALUNO)
        m3 = await TenantFactory.create_member(session, tenant_id=tenant.id, user_id=user3.id, role=UserRole.ALUNO)

        sc_repo = SubjectClassSQLAlchemyRepository(session)
        sc = await sc_repo.save(SubjectClass(tenant_id=tenant.id, name="Turma C", discipline_name="History"))

        repo = EnrollmentSQLAlchemyRepository(session)
        e1 = await repo.save(Enrollment(subject_class_id=sc.id, tenant_member_id=m1.id, status=EnrollmentStatus.ACTIVE))
        e2 = await repo.save(Enrollment(subject_class_id=sc.id, tenant_member_id=m2.id, status=EnrollmentStatus.DROPPED))
        e3 = await repo.save(Enrollment(subject_class_id=sc.id, tenant_member_id=m3.id, status=EnrollmentStatus.ACTIVE, deleted=True))

        active_list = await repo.list_by_subject_class(sc.id, status=EnrollmentStatus.ACTIVE)
        assert len(active_list) == 1
        assert active_list[0].id == e1.id

        non_deleted_list = await repo.list_by_subject_class(sc.id)
        assert len(non_deleted_list) == 2

        all_list = await repo.list_by_subject_class(sc.id, include_deleted=True)
        assert len(all_list) == 3

    async def test_drop_all_active_for_member(self, session):
        """Deve alterar em lote o status de todas as matrículas ativas de um membro para DROPPED."""
        user = await UserFactory.create(session)
        tenant = await TenantFactory.create(session)
        member = await TenantFactory.create_member(session, tenant_id=tenant.id, user_id=user.id, role=UserRole.ALUNO)

        sc_repo = SubjectClassSQLAlchemyRepository(session)
        sc1 = await sc_repo.save(SubjectClass(tenant_id=tenant.id, name="T1", discipline_name="D1"))
        sc2 = await sc_repo.save(SubjectClass(tenant_id=tenant.id, name="T2", discipline_name="D2"))

        repo = EnrollmentSQLAlchemyRepository(session)
        e1 = await repo.save(Enrollment(subject_class_id=sc1.id, tenant_member_id=member.id, status=EnrollmentStatus.ACTIVE))
        e2 = await repo.save(Enrollment(subject_class_id=sc2.id, tenant_member_id=member.id, status=EnrollmentStatus.ACTIVE))

        affected_count = await repo.drop_all_active_for_member(member.id)
        assert affected_count == 2

        res_e1 = await repo.find_by_id(e1.id)
        res_e2 = await repo.find_by_id(e2.id)
        assert res_e1 is not None
        assert res_e2 is not None
        assert res_e1.status == EnrollmentStatus.DROPPED
        assert res_e2.status == EnrollmentStatus.DROPPED
        assert res_e1.dropped_at is not None
        assert res_e1.drop_reason is not None
        assert res_e1.drop_reason == DropReason.ROLE_CHANGE

    async def test_list_by_member(self, session):
        """Deve listar todas as matrículas de um aluno específico."""
        user = await UserFactory.create(session)
        tenant = await TenantFactory.create(session)
        member = await TenantFactory.create_member(session, tenant_id=tenant.id, user_id=user.id, role=UserRole.ALUNO)

        sc_repo = SubjectClassSQLAlchemyRepository(session)
        sc1 = await sc_repo.save(SubjectClass(tenant_id=tenant.id, name="T1", discipline_name="D1"))
        sc2 = await sc_repo.save(SubjectClass(tenant_id=tenant.id, name="T2", discipline_name="D2"))

        repo = EnrollmentSQLAlchemyRepository(session)
        await repo.save(Enrollment(subject_class_id=sc1.id, tenant_member_id=member.id, status=EnrollmentStatus.ACTIVE))
        await repo.save(Enrollment(subject_class_id=sc2.id, tenant_member_id=member.id, status=EnrollmentStatus.DROPPED))

        member_list = await repo.list_by_member(member.id)
        assert len(member_list) == 2

    async def test_partial_unique_index_allows_new_enrollment_after_soft_delete(self, session):
        """O partial unique index 'uq_enrollment_active' deve impedir duplicidade de ativos, mas permitir nova matrícula se a anterior tiver deleted=True."""
        user = await UserFactory.create(session)
        tenant = await TenantFactory.create(session)
        member = await TenantFactory.create_member(session, tenant_id=tenant.id, user_id=user.id, role=UserRole.ALUNO)

        sc_repo = SubjectClassSQLAlchemyRepository(session)
        sc = await sc_repo.save(SubjectClass(tenant_id=tenant.id, name="Turma Index", discipline_name="Test"))

        repo = EnrollmentSQLAlchemyRepository(session)
        # 1. Primeira matrícula ativa
        e1 = await repo.save(Enrollment(subject_class_id=sc.id, tenant_member_id=member.id))

        # 2. Tentar inserir segunda matrícula idêntica em savepoint deve falhar pelo partial index
        async with session.begin_nested():
            e2_duplicate = Enrollment(subject_class_id=sc.id, tenant_member_id=member.id)
            with pytest.raises(IntegrityError):
                await repo.save(e2_duplicate)

        # 3. Soft-delete da primeira matrícula
        e1.deleted = True
        await repo.save(e1)

        # 4. Nova matrícula idêntica agora DEVE funcionar devido ao postgresql_where deleted = false
        e3_new = Enrollment(subject_class_id=sc.id, tenant_member_id=member.id)
        saved_e3 = await repo.save(e3_new)
        assert saved_e3.id is not None
        assert saved_e3.id != e1.id
