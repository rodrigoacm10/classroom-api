from uuid import uuid4

import pytest

from modules.enrollment.application.use_cases.get_student_metrics import (
    GetStudentMetricsInput,
    GetStudentMetricsUseCase,
)
from modules.enrollment.domain.entities.student_subject_class_summary import (
    StudentSubjectClassSummary,
)
from modules.tenant.domain.entities.tenant_member import TenantMember
from shared.enums.enrollment_status import EnrollmentStatus
from shared.enums.user_role import UserRole
from shared.exceptions import (
    BusinessRuleException,
    ForbiddenException,
    ResourceNotFoundException,
)
from tests.unit.fakes.fake_enrollment_repository import FakeEnrollmentRepository
from tests.unit.fakes.fake_tenant_member_repository import FakeTenantMemberRepository


@pytest.mark.asyncio
class TestGetStudentMetricsUseCase:
    async def test_get_student_metrics_by_member_id_success(self):
        """Calcula corretamente turmas, média de frequência e turmas em risco (< 75%)."""
        enrollment_repo = FakeEnrollmentRepository()
        member_repo = FakeTenantMemberRepository()

        tenant_id = uuid4()
        member = TenantMember(tenant_id=tenant_id, user_id=uuid4(), role=UserRole.ALUNO)
        await member_repo.save(member)

        summaries = [
            StudentSubjectClassSummary(
                enrollment_id=uuid4(),
                subject_class_id=uuid4(),
                name="Cálculo I",
                discipline_name="Matemática",
                room_id=None,
                room_name=None,
                professor_id=None,
                professor_name=None,
                attendance_rate=0.90,
                status=EnrollmentStatus.ACTIVE,
                total_sessions=10,
                absences_count=1,
            ),
            StudentSubjectClassSummary(
                enrollment_id=uuid4(),
                subject_class_id=uuid4(),
                name="Física I",
                discipline_name="Física",
                room_id=None,
                room_name=None,
                professor_id=None,
                professor_name=None,
                attendance_rate=0.80,
                status=EnrollmentStatus.ACTIVE,
                total_sessions=10,
                absences_count=2,
            ),
            StudentSubjectClassSummary(
                enrollment_id=uuid4(),
                subject_class_id=uuid4(),
                name="Algoritmos",
                discipline_name="Computação",
                room_id=None,
                room_name=None,
                professor_id=None,
                professor_name=None,
                attendance_rate=0.60,  # Em risco (< 0.75)
                status=EnrollmentStatus.ACTIVE,
                total_sessions=10,
                absences_count=4,
            ),
        ]
        enrollment_repo.set_summaries(member.id, summaries)

        use_case = GetStudentMetricsUseCase(
            enrollment_repo=enrollment_repo,
            member_repo=member_repo,
        )
        metrics = await use_case.execute(
            GetStudentMetricsInput(
                tenant_id=tenant_id,
                tenant_member_id=member.id,
            )
        )

        assert metrics.total_classes == 3
        assert metrics.at_risk_count == 1
        assert metrics.average_attendance_rate == round((0.90 + 0.80 + 0.60) / 3, 4)

    async def test_get_student_metrics_by_user_id_success(self):
        """Resolve o aluno via user_id e retorna os indicadores com sucesso."""
        enrollment_repo = FakeEnrollmentRepository()
        member_repo = FakeTenantMemberRepository()

        tenant_id = uuid4()
        user_id = uuid4()
        member = TenantMember(tenant_id=tenant_id, user_id=user_id, role=UserRole.ALUNO)
        await member_repo.save(member)

        summaries = [
            StudentSubjectClassSummary(
                enrollment_id=uuid4(),
                subject_class_id=uuid4(),
                name="Estrutura de Dados",
                discipline_name="Computação",
                room_id=None,
                room_name=None,
                professor_id=None,
                professor_name=None,
                attendance_rate=0.95,
                status=EnrollmentStatus.ACTIVE,
                total_sessions=8,
                absences_count=0,
            ),
        ]
        enrollment_repo.set_summaries(member.id, summaries)

        use_case = GetStudentMetricsUseCase(
            enrollment_repo=enrollment_repo,
            member_repo=member_repo,
        )
        metrics = await use_case.execute(
            GetStudentMetricsInput(
                tenant_id=tenant_id,
                user_id=user_id,
            )
        )

        assert metrics.total_classes == 1
        assert metrics.average_attendance_rate == 0.95
        assert metrics.at_risk_count == 0

    async def test_get_student_metrics_zero_sessions_held(self):
        """Turmas sem sessões registradas não devem ser marcadas em risco nem zerar a média."""
        enrollment_repo = FakeEnrollmentRepository()
        member_repo = FakeTenantMemberRepository()

        tenant_id = uuid4()
        member = TenantMember(tenant_id=tenant_id, user_id=uuid4(), role=UserRole.ALUNO)
        await member_repo.save(member)

        summaries = [
            StudentSubjectClassSummary(
                enrollment_id=uuid4(),
                subject_class_id=uuid4(),
                name="Cálculo II",
                discipline_name="Matemática",
                room_id=None,
                room_name=None,
                professor_id=None,
                professor_name=None,
                attendance_rate=0.0,
                status=EnrollmentStatus.ACTIVE,
                total_sessions=0,
                absences_count=0,
            ),
        ]
        enrollment_repo.set_summaries(member.id, summaries)

        use_case = GetStudentMetricsUseCase(
            enrollment_repo=enrollment_repo,
            member_repo=member_repo,
        )
        metrics = await use_case.execute(
            GetStudentMetricsInput(
                tenant_id=tenant_id,
                tenant_member_id=member.id,
            )
        )

        assert metrics.total_classes == 1
        assert metrics.average_attendance_rate == 1.0
        assert metrics.at_risk_count == 0

    async def test_get_student_metrics_no_classes_enrolled(self):
        """Aluno sem nenhuma matrícula deve ter total_classes=0 e 0 em risco."""
        enrollment_repo = FakeEnrollmentRepository()
        member_repo = FakeTenantMemberRepository()

        tenant_id = uuid4()
        member = TenantMember(tenant_id=tenant_id, user_id=uuid4(), role=UserRole.ALUNO)
        await member_repo.save(member)

        use_case = GetStudentMetricsUseCase(
            enrollment_repo=enrollment_repo,
            member_repo=member_repo,
        )
        metrics = await use_case.execute(
            GetStudentMetricsInput(
                tenant_id=tenant_id,
                tenant_member_id=member.id,
            )
        )

        assert metrics.total_classes == 0
        assert metrics.average_attendance_rate == 1.0
        assert metrics.at_risk_count == 0

    async def test_get_student_metrics_user_not_found(self):
        """Deve lançar ForbiddenException caso user_id não seja membro do tenant."""
        use_case = GetStudentMetricsUseCase(
            enrollment_repo=FakeEnrollmentRepository(),
            member_repo=FakeTenantMemberRepository(),
        )
        with pytest.raises(ForbiddenException, match="Aluno não encontrado nesta instituição."):
            await use_case.execute(
                GetStudentMetricsInput(
                    tenant_id=uuid4(),
                    user_id=uuid4(),
                )
            )

    async def test_get_student_metrics_member_not_found(self):
        """Deve lançar ResourceNotFoundException se member_id não existir."""
        use_case = GetStudentMetricsUseCase(
            enrollment_repo=FakeEnrollmentRepository(),
            member_repo=FakeTenantMemberRepository(),
        )
        with pytest.raises(ResourceNotFoundException, match="Membro não encontrado."):
            await use_case.execute(
                GetStudentMetricsInput(
                    tenant_id=uuid4(),
                    tenant_member_id=uuid4(),
                )
            )

    async def test_get_student_metrics_member_wrong_tenant(self):
        """Deve lançar BusinessRuleException se o membro for de outro tenant."""
        member_repo = FakeTenantMemberRepository()
        member = TenantMember(tenant_id=uuid4(), user_id=uuid4(), role=UserRole.ALUNO)
        await member_repo.save(member)

        use_case = GetStudentMetricsUseCase(
            enrollment_repo=FakeEnrollmentRepository(),
            member_repo=member_repo,
        )
        with pytest.raises(
            BusinessRuleException, match="O membro não pertence a esta instituição."
        ):
            await use_case.execute(
                GetStudentMetricsInput(
                    tenant_id=uuid4(),
                    tenant_member_id=member.id,
                )
            )

    async def test_get_student_metrics_missing_identifiers(self):
        """Deve lançar BusinessRuleException se nem user_id nem tenant_member_id forem fornecidos."""
        use_case = GetStudentMetricsUseCase(
            enrollment_repo=FakeEnrollmentRepository(),
            member_repo=FakeTenantMemberRepository(),
        )
        with pytest.raises(
            BusinessRuleException, match="É necessário informar tenant_member_id ou user_id."
        ):
            await use_case.execute(GetStudentMetricsInput(tenant_id=uuid4()))

    async def test_get_student_metrics_mixed_classes_with_and_without_sessions(self):
        """Classes sem sessões não interferem no cálculo da média das turmas com sessões."""
        enrollment_repo = FakeEnrollmentRepository()
        member_repo = FakeTenantMemberRepository()

        tenant_id = uuid4()
        member = TenantMember(tenant_id=tenant_id, user_id=uuid4(), role=UserRole.ALUNO)
        await member_repo.save(member)

        summaries = [
            StudentSubjectClassSummary(
                enrollment_id=uuid4(),
                subject_class_id=uuid4(),
                name="Estrutura de Dados",
                discipline_name="Computação",
                room_id=None,
                room_name=None,
                professor_id=None,
                professor_name=None,
                attendance_rate=0.80,
                status=EnrollmentStatus.ACTIVE,
                total_sessions=10,
                absences_count=2,
            ),
            StudentSubjectClassSummary(
                enrollment_id=uuid4(),
                subject_class_id=uuid4(),
                name="Sistemas Operacionais",
                discipline_name="Computação",
                room_id=None,
                room_name=None,
                professor_id=None,
                professor_name=None,
                attendance_rate=0.0,
                status=EnrollmentStatus.ACTIVE,
                total_sessions=0,  # Sem sessões ainda
                absences_count=0,
            ),
        ]
        enrollment_repo.set_summaries(member.id, summaries)

        use_case = GetStudentMetricsUseCase(
            enrollment_repo=enrollment_repo,
            member_repo=member_repo,
        )
        metrics = await use_case.execute(
            GetStudentMetricsInput(tenant_id=tenant_id, tenant_member_id=member.id)
        )

        assert metrics.total_classes == 2
        # Apenas a turma com sessões define a média
        assert metrics.average_attendance_rate == 0.80
        assert metrics.at_risk_count == 0

    async def test_get_student_metrics_multiple_at_risk_classes(self):
        """Identifica corretamente quando múltiplas turmas estão abaixo de 75%."""
        enrollment_repo = FakeEnrollmentRepository()
        member_repo = FakeTenantMemberRepository()

        tenant_id = uuid4()
        member = TenantMember(tenant_id=tenant_id, user_id=uuid4(), role=UserRole.ALUNO)
        await member_repo.save(member)

        summaries = [
            StudentSubjectClassSummary(
                enrollment_id=uuid4(),
                subject_class_id=uuid4(),
                name="Cálculo I",
                discipline_name="Matemática",
                room_id=None,
                room_name=None,
                professor_id=None,
                professor_name=None,
                attendance_rate=0.70,  # Em risco (< 0.75)
                status=EnrollmentStatus.ACTIVE,
                total_sessions=10,
                absences_count=3,
            ),
            StudentSubjectClassSummary(
                enrollment_id=uuid4(),
                subject_class_id=uuid4(),
                name="Física I",
                discipline_name="Física",
                room_id=None,
                room_name=None,
                professor_id=None,
                professor_name=None,
                attendance_rate=0.50,  # Em risco (< 0.75)
                status=EnrollmentStatus.ACTIVE,
                total_sessions=10,
                absences_count=5,
            ),
        ]
        enrollment_repo.set_summaries(member.id, summaries)

        use_case = GetStudentMetricsUseCase(
            enrollment_repo=enrollment_repo,
            member_repo=member_repo,
        )
        metrics = await use_case.execute(
            GetStudentMetricsInput(tenant_id=tenant_id, tenant_member_id=member.id)
        )

        assert metrics.total_classes == 2
        assert metrics.at_risk_count == 2
        assert metrics.average_attendance_rate == 0.60

    async def test_get_student_metrics_deleted_member_forbidden(self):
        """Deve lançar ForbiddenException caso o membro esteja deletado."""
        member_repo = FakeTenantMemberRepository()
        tenant_id = uuid4()
        user_id = uuid4()
        member = TenantMember(
            tenant_id=tenant_id, user_id=user_id, role=UserRole.ALUNO, deleted=True
        )
        await member_repo.save(member)

        use_case = GetStudentMetricsUseCase(
            enrollment_repo=FakeEnrollmentRepository(),
            member_repo=member_repo,
        )
        with pytest.raises(ForbiddenException, match="Aluno não encontrado nesta instituição."):
            await use_case.execute(GetStudentMetricsInput(tenant_id=tenant_id, user_id=user_id))
