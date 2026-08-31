from uuid import uuid4

import pytest

from modules.enrollment.application.use_cases.delete_enrollment import (
    DeleteEnrollmentInput,
    DeleteEnrollmentUseCase,
)
from modules.enrollment.application.use_cases.drop_enrollment import (
    DropEnrollmentInput,
    DropEnrollmentUseCase,
)
from modules.enrollment.application.use_cases.enroll_student import (
    EnrollStudentInput,
    EnrollStudentUseCase,
)
from modules.enrollment.application.use_cases.list_enrollments import (
    ListEnrollmentsInput,
    ListEnrollmentsUseCase,
)
from modules.enrollment.domain.entities.enrollment import Enrollment
from modules.subject_class.domain.entities.subject_class import SubjectClass
from modules.tenant.application.use_cases.update_tenant_member_role import (
    UpdateTenantMemberRoleInput,
    UpdateTenantMemberRoleUseCase,
)
from modules.tenant.domain.entities.tenant import Tenant
from modules.tenant.domain.entities.tenant_member import TenantMember
from shared.enums.enrollment_status import EnrollmentStatus
from shared.enums.user_role import UserRole
from shared.exceptions import (
    BusinessRuleException,
    ResourceAlreadyExistsException,
    ResourceNotFoundException,
)
from tests.unit.fakes.fake_enrollment_repository import FakeEnrollmentRepository
from tests.unit.fakes.fake_subject_class_repository import FakeSubjectClassRepository
from tests.unit.fakes.fake_tenant_member_repository import FakeTenantMemberRepository
from tests.unit.fakes.fake_tenant_repository import FakeTenantRepository


@pytest.mark.asyncio
class TestEnrollmentUseCases:

    async def test_enroll_student_success(self):
        """Matricular aluno válido deve retornar Enrollment com status=active e deleted=false."""
        enrollment_repo = FakeEnrollmentRepository()
        subject_class_repo = FakeSubjectClassRepository()
        member_repo = FakeTenantMemberRepository()

        tenant_id = uuid4()
        subject_class = SubjectClass(tenant_id=tenant_id, name="Turma 1", discipline_name="Math")
        await subject_class_repo.save(subject_class)

        member = TenantMember(tenant_id=tenant_id, user_id=uuid4(), role=UserRole.ALUNO)
        await member_repo.save(member)

        use_case = EnrollStudentUseCase(
            enrollment_repo=enrollment_repo,
            subject_class_repo=subject_class_repo,
            member_repo=member_repo,
        )

        result = await use_case.execute(
            EnrollStudentInput(
                subject_class_id=subject_class.id,
                tenant_member_id=member.id,
                tenant_id=tenant_id,
            )
        )

        assert result.id is not None
        assert result.subject_class_id == subject_class.id
        assert result.tenant_member_id == member.id
        assert result.status == EnrollmentStatus.ACTIVE
        assert result.deleted is False

    async def test_enroll_student_with_non_aluno_role_fails(self):
        """Matricular membro com papel PROFESSOR deve lançar BusinessRuleException."""
        enrollment_repo = FakeEnrollmentRepository()
        subject_class_repo = FakeSubjectClassRepository()
        member_repo = FakeTenantMemberRepository()

        tenant_id = uuid4()
        subject_class = SubjectClass(tenant_id=tenant_id, name="Turma 1", discipline_name="Math")
        await subject_class_repo.save(subject_class)

        member = TenantMember(tenant_id=tenant_id, user_id=uuid4(), role=UserRole.PROFESSOR)
        await member_repo.save(member)

        use_case = EnrollStudentUseCase(
            enrollment_repo=enrollment_repo,
            subject_class_repo=subject_class_repo,
            member_repo=member_repo,
        )

        with pytest.raises(BusinessRuleException, match="Apenas alunos podem ser matriculados"):
            await use_case.execute(
                EnrollStudentInput(
                    subject_class_id=subject_class.id,
                    tenant_member_id=member.id,
                    tenant_id=tenant_id,
                )
            )

    async def test_enroll_student_from_different_tenant_fails(self):
        """Matricular membro pertencente a outra instituição deve lançar BusinessRuleException."""
        enrollment_repo = FakeEnrollmentRepository()
        subject_class_repo = FakeSubjectClassRepository()
        member_repo = FakeTenantMemberRepository()

        tenant_id = uuid4()
        other_tenant_id = uuid4()

        subject_class = SubjectClass(tenant_id=tenant_id, name="Turma 1", discipline_name="Math")
        await subject_class_repo.save(subject_class)

        member = TenantMember(tenant_id=other_tenant_id, user_id=uuid4(), role=UserRole.ALUNO)
        await member_repo.save(member)

        use_case = EnrollStudentUseCase(
            enrollment_repo=enrollment_repo,
            subject_class_repo=subject_class_repo,
            member_repo=member_repo,
        )

        with pytest.raises(BusinessRuleException, match="não pertence a esta instituição"):
            await use_case.execute(
                EnrollStudentInput(
                    subject_class_id=subject_class.id,
                    tenant_member_id=member.id,
                    tenant_id=tenant_id,
                )
            )

    async def test_enroll_already_active_student_fails(self):
        """Matricular aluno já ativo na turma deve lançar BusinessRuleException (409)."""
        enrollment_repo = FakeEnrollmentRepository()
        subject_class_repo = FakeSubjectClassRepository()
        member_repo = FakeTenantMemberRepository()

        tenant_id = uuid4()
        subject_class = SubjectClass(tenant_id=tenant_id, name="Turma 1", discipline_name="Math")
        await subject_class_repo.save(subject_class)

        member = TenantMember(tenant_id=tenant_id, user_id=uuid4(), role=UserRole.ALUNO)
        await member_repo.save(member)

        use_case = EnrollStudentUseCase(
            enrollment_repo=enrollment_repo,
            subject_class_repo=subject_class_repo,
            member_repo=member_repo,
        )

        await use_case.execute(
            EnrollStudentInput(
                subject_class_id=subject_class.id,
                tenant_member_id=member.id,
                tenant_id=tenant_id,
            )
        )

        with pytest.raises(ResourceAlreadyExistsException, match="já está matriculado"):
            await use_case.execute(
                EnrollStudentInput(
                    subject_class_id=subject_class.id,
                    tenant_member_id=member.id,
                    tenant_id=tenant_id,
                )
            )

    async def test_enroll_student_reactivates_dropped_enrollment(self):
        """Matricular aluno que havia sido 'dropped' deve reativar a matrícula existente (status=active)."""
        enrollment_repo = FakeEnrollmentRepository()
        subject_class_repo = FakeSubjectClassRepository()
        member_repo = FakeTenantMemberRepository()

        tenant_id = uuid4()
        subject_class = SubjectClass(tenant_id=tenant_id, name="Turma 1", discipline_name="Math")
        await subject_class_repo.save(subject_class)

        member = TenantMember(tenant_id=tenant_id, user_id=uuid4(), role=UserRole.ALUNO)
        await member_repo.save(member)

        existing = Enrollment(
            subject_class_id=subject_class.id,
            tenant_member_id=member.id,
            status=EnrollmentStatus.DROPPED,
        )
        await enrollment_repo.save(existing)

        use_case = EnrollStudentUseCase(
            enrollment_repo=enrollment_repo,
            subject_class_repo=subject_class_repo,
            member_repo=member_repo,
        )

        result = await use_case.execute(
            EnrollStudentInput(
                subject_class_id=subject_class.id,
                tenant_member_id=member.id,
                tenant_id=tenant_id,
            )
        )

        assert result.id == existing.id
        assert result.status == EnrollmentStatus.ACTIVE

    async def test_enroll_student_creates_new_if_previous_was_deleted(self):
        """Matricular aluno após um soft delete (deleted=True) deve criar um novo registro."""
        enrollment_repo = FakeEnrollmentRepository()
        subject_class_repo = FakeSubjectClassRepository()
        member_repo = FakeTenantMemberRepository()

        tenant_id = uuid4()
        subject_class = SubjectClass(tenant_id=tenant_id, name="Turma 1", discipline_name="Math")
        await subject_class_repo.save(subject_class)

        member = TenantMember(tenant_id=tenant_id, user_id=uuid4(), role=UserRole.ALUNO)
        await member_repo.save(member)

        old_deleted = Enrollment(
            subject_class_id=subject_class.id,
            tenant_member_id=member.id,
            deleted=True,
        )
        await enrollment_repo.save(old_deleted)

        use_case = EnrollStudentUseCase(
            enrollment_repo=enrollment_repo,
            subject_class_repo=subject_class_repo,
            member_repo=member_repo,
        )

        result = await use_case.execute(
            EnrollStudentInput(
                subject_class_id=subject_class.id,
                tenant_member_id=member.id,
                tenant_id=tenant_id,
            )
        )

        assert result.id != old_deleted.id
        assert result.status == EnrollmentStatus.ACTIVE
        assert result.deleted is False

    async def test_enroll_student_in_nonexistent_class_fails(self):
        """Matricular em turma inexistente deve lançar ResourceNotFoundException."""
        enrollment_repo = FakeEnrollmentRepository()
        subject_class_repo = FakeSubjectClassRepository()
        member_repo = FakeTenantMemberRepository()

        use_case = EnrollStudentUseCase(
            enrollment_repo=enrollment_repo,
            subject_class_repo=subject_class_repo,
            member_repo=member_repo,
        )

        with pytest.raises(ResourceNotFoundException, match="Turma não encontrada"):
            await use_case.execute(
                EnrollStudentInput(
                    subject_class_id=uuid4(),
                    tenant_member_id=uuid4(),
                    tenant_id=uuid4(),
                )
            )

    async def test_drop_enrollment_success(self):
        """Cancelar matrícula ativa via DropEnrollmentUseCase deve mudar status para DROPPED."""
        enrollment_repo = FakeEnrollmentRepository()
        subject_class_id = uuid4()
        member_id = uuid4()

        enrollment = Enrollment(
            subject_class_id=subject_class_id,
            tenant_member_id=member_id,
            status=EnrollmentStatus.ACTIVE,
        )
        await enrollment_repo.save(enrollment)

        use_case = DropEnrollmentUseCase(enrollment_repo=enrollment_repo)
        await use_case.execute(
            DropEnrollmentInput(
                enrollment_id=enrollment.id,
                subject_class_id=subject_class_id,
            )
        )

        updated = await enrollment_repo.find_by_id(enrollment.id)
        assert updated is not None
        assert updated.status == EnrollmentStatus.DROPPED

    async def test_drop_already_dropped_enrollment_fails(self):
        """Cancelar matrícula já em DROPPED deve lançar BusinessRuleException."""
        enrollment_repo = FakeEnrollmentRepository()
        subject_class_id = uuid4()
        member_id = uuid4()

        enrollment = Enrollment(
            subject_class_id=subject_class_id,
            tenant_member_id=member_id,
            status=EnrollmentStatus.DROPPED,
        )
        await enrollment_repo.save(enrollment)

        use_case = DropEnrollmentUseCase(enrollment_repo=enrollment_repo)
        with pytest.raises(BusinessRuleException, match="já está cancelada"):
            await use_case.execute(
                DropEnrollmentInput(
                    enrollment_id=enrollment.id,
                    subject_class_id=subject_class_id,
                )
            )

    async def test_delete_enrollment_success(self):
        """Soft delete via DeleteEnrollmentUseCase deve definir deleted=True."""
        enrollment_repo = FakeEnrollmentRepository()
        subject_class_id = uuid4()
        member_id = uuid4()

        enrollment = Enrollment(
            subject_class_id=subject_class_id,
            tenant_member_id=member_id,
        )
        await enrollment_repo.save(enrollment)

        use_case = DeleteEnrollmentUseCase(enrollment_repo=enrollment_repo)
        await use_case.execute(
            DeleteEnrollmentInput(
                enrollment_id=enrollment.id,
                subject_class_id=subject_class_id,
            )
        )

        # Sem include_deleted deve retornar None
        assert await enrollment_repo.find_by_id(enrollment.id, include_deleted=False) is None
        # Com include_deleted deve estar deleted=True
        deleted_record = await enrollment_repo.find_by_id(enrollment.id, include_deleted=True)
        assert deleted_record is not None
        assert deleted_record.deleted is True

    async def test_list_enrollments_filters(self):
        """ListEnrollmentsUseCase deve filtrar por status e respeitar include_deleted."""
        enrollment_repo = FakeEnrollmentRepository()
        subject_class_repo = FakeSubjectClassRepository()

        tenant_id = uuid4()
        subject_class = SubjectClass(tenant_id=tenant_id, name="Turma 1", discipline_name="Math")
        await subject_class_repo.save(subject_class)

        e1 = Enrollment(subject_class_id=subject_class.id, tenant_member_id=uuid4(), status=EnrollmentStatus.ACTIVE)
        e2 = Enrollment(subject_class_id=subject_class.id, tenant_member_id=uuid4(), status=EnrollmentStatus.DROPPED)
        e3 = Enrollment(subject_class_id=subject_class.id, tenant_member_id=uuid4(), status=EnrollmentStatus.ACTIVE, deleted=True)

        await enrollment_repo.save(e1)
        await enrollment_repo.save(e2)
        await enrollment_repo.save(e3)

        use_case = ListEnrollmentsUseCase(
            enrollment_repo=enrollment_repo,
            subject_class_repo=subject_class_repo,
        )

        # 1. Apenas ativos
        active_list = await use_case.execute(
            ListEnrollmentsInput(
                subject_class_id=subject_class.id,
                tenant_id=tenant_id,
                status=EnrollmentStatus.ACTIVE,
            )
        )
        assert len(active_list) == 1
        assert active_list[0].id == e1.id

        # 2. Todos os não deletados
        all_non_deleted = await use_case.execute(
            ListEnrollmentsInput(
                subject_class_id=subject_class.id,
                tenant_id=tenant_id,
            )
        )
        assert len(all_non_deleted) == 2

        # 3. Incluindo deletados
        all_with_deleted = await use_case.execute(
            ListEnrollmentsInput(
                subject_class_id=subject_class.id,
                tenant_id=tenant_id,
                include_deleted=True,
            )
        )
        assert len(all_with_deleted) == 3

    async def test_role_change_from_aluno_drops_active_enrollments(self):
        """Quando a role do membro muda de ALUNO para PROFESSOR/ADMIN, suas matrículas ativas ficam DROPPED."""
        enrollment_repo = FakeEnrollmentRepository()
        tenant_repo = FakeTenantRepository()
        member_repo = FakeTenantMemberRepository()

        tenant = Tenant(name="Escola A", slug="escola-a")
        await tenant_repo.save(tenant)

        # Admin para executar a troca se necessário, e o aluno
        admin_member = TenantMember(tenant_id=tenant.id, user_id=uuid4(), role=UserRole.ADMIN)
        await member_repo.save(admin_member)

        aluno_user_id = uuid4()
        aluno_member = TenantMember(tenant_id=tenant.id, user_id=aluno_user_id, role=UserRole.ALUNO)
        await member_repo.save(aluno_member)

        e1 = Enrollment(subject_class_id=uuid4(), tenant_member_id=aluno_member.id, status=EnrollmentStatus.ACTIVE)
        e2 = Enrollment(subject_class_id=uuid4(), tenant_member_id=aluno_member.id, status=EnrollmentStatus.ACTIVE)
        await enrollment_repo.save(e1)
        await enrollment_repo.save(e2)

        use_case = UpdateTenantMemberRoleUseCase(
            tenant_repo=tenant_repo,
            member_repo=member_repo,
            enrollment_repo=enrollment_repo,
        )

        await use_case.execute(
            UpdateTenantMemberRoleInput(
                tenant_id=tenant.id,
                user_id_to_update=aluno_user_id,
                new_role=UserRole.PROFESSOR,
            )
        )

        res_e1 = await enrollment_repo.find_by_id(e1.id)
        res_e2 = await enrollment_repo.find_by_id(e2.id)

        assert res_e1 is not None
        assert res_e2 is not None
        assert res_e1.status == EnrollmentStatus.DROPPED
        assert res_e2.status == EnrollmentStatus.DROPPED
