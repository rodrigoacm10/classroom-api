from datetime import datetime, timezone
from uuid import uuid4

import pytest

from modules.subject_class.application.use_cases.get_subject_class_metrics import (
    GetSubjectClassMetricsInput,
    GetSubjectClassMetricsUseCase,
)
from modules.subject_class.domain.entities.subject_class import SubjectClass
from modules.tenant.domain.entities.tenant import Tenant
from modules.tenant.domain.entities.tenant_member import TenantMember
from shared.enums.user_role import UserRole
from shared.exceptions import ForbiddenException, ResourceNotFoundException
from tests.unit.fakes.fake_subject_class_repository import FakeSubjectClassRepository
from tests.unit.fakes.fake_tenant_member_repository import FakeTenantMemberRepository
from tests.unit.fakes.fake_tenant_repository import FakeTenantRepository


class TestGetSubjectClassMetricsUseCase:
    @pytest.fixture
    def setup_use_case(self):
        subject_class_repo = FakeSubjectClassRepository()
        tenant_repo = FakeTenantRepository()
        member_repo = FakeTenantMemberRepository()
        use_case = GetSubjectClassMetricsUseCase(
            subject_class_repo=subject_class_repo,
            tenant_repo=tenant_repo,
            member_repo=member_repo,
        )
        return {
            "use_case": use_case,
            "subject_class_repo": subject_class_repo,
            "tenant_repo": tenant_repo,
            "member_repo": member_repo,
        }

    async def test_get_metrics_as_admin_success(self, setup_use_case):
        use_case = setup_use_case["use_case"]
        tenant_repo = setup_use_case["tenant_repo"]
        sc_repo = setup_use_case["subject_class_repo"]

        tenant = Tenant(name="UFPE", slug="ufpe")
        await tenant_repo.save(tenant)

        # Turma 1: ativa
        sc1 = SubjectClass(
            tenant_id=tenant.id,
            professor_id=uuid4(),
            room_id=uuid4(),
            name="Turma A",
            discipline_name="Cálculo 1",
            active=True,
        )
        # Turma 2: inativa
        sc2 = SubjectClass(
            tenant_id=tenant.id,
            professor_id=uuid4(),
            room_id=uuid4(),
            name="Turma B",
            discipline_name="Cálculo 2",
            active=False,
        )
        await sc_repo.save(sc1)
        await sc_repo.save(sc2)

        input_data = GetSubjectClassMetricsInput(
            tenant_id=tenant.id,
            user_id=uuid4(),
            user_role=UserRole.ADMIN,
        )
        metrics = await use_case.execute(input_data)

        assert metrics.total_classes == 2
        assert metrics.active_classes == 1
        assert metrics.inactive_classes == 1
        assert metrics.total_students == 0
        assert metrics.average_attendance_rate == 0.0
        assert metrics.at_risk_classes_count == 1
        assert metrics.live_classes_count == 0

    async def test_get_metrics_as_professor_scopes_to_own_classes(self, setup_use_case):
        use_case = setup_use_case["use_case"]
        tenant_repo = setup_use_case["tenant_repo"]
        member_repo = setup_use_case["member_repo"]
        sc_repo = setup_use_case["subject_class_repo"]

        tenant = Tenant(name="UFRPE", slug="ufrpe")
        await tenant_repo.save(tenant)

        prof_user_id = uuid4()
        prof_member = TenantMember(
            tenant_id=tenant.id,
            user_id=prof_user_id,
            role=UserRole.PROFESSOR,
        )
        await member_repo.save(prof_member)

        other_member_id = uuid4()

        # Turma do professor
        sc_prof = SubjectClass(
            tenant_id=tenant.id,
            professor_id=prof_member.id,
            room_id=uuid4(),
            name="Turma Prof",
            discipline_name="Algoritmos",
            active=True,
        )
        # Turma de outro professor
        sc_other = SubjectClass(
            tenant_id=tenant.id,
            professor_id=other_member_id,
            room_id=uuid4(),
            name="Turma Outro",
            discipline_name="Física",
            active=True,
        )
        await sc_repo.save(sc_prof)
        await sc_repo.save(sc_other)

        input_data = GetSubjectClassMetricsInput(
            tenant_id=tenant.id,
            user_id=prof_user_id,
            user_role=UserRole.PROFESSOR,
        )
        metrics = await use_case.execute(input_data)

        # Deve ver apenas a sua turma
        assert metrics.total_classes == 1
        assert metrics.active_classes == 1

    async def test_get_metrics_student_role_forbidden(self, setup_use_case):
        use_case = setup_use_case["use_case"]
        tenant_repo = setup_use_case["tenant_repo"]

        tenant = Tenant(name="UFPE", slug="ufpe")
        await tenant_repo.save(tenant)

        input_data = GetSubjectClassMetricsInput(
            tenant_id=tenant.id,
            user_id=uuid4(),
            user_role=UserRole.ALUNO,
        )
        with pytest.raises(ForbiddenException):
            await use_case.execute(input_data)

    async def test_get_metrics_tenant_not_found(self, setup_use_case):
        use_case = setup_use_case["use_case"]

        input_data = GetSubjectClassMetricsInput(
            tenant_id=uuid4(),
            user_id=uuid4(),
            user_role=UserRole.ADMIN,
        )
        with pytest.raises(ResourceNotFoundException):
            await use_case.execute(input_data)

    async def test_get_metrics_professor_member_not_found(self, setup_use_case):
        use_case = setup_use_case["use_case"]
        tenant_repo = setup_use_case["tenant_repo"]

        tenant = Tenant(name="UFPE", slug="ufpe")
        await tenant_repo.save(tenant)

        input_data = GetSubjectClassMetricsInput(
            tenant_id=tenant.id,
            user_id=uuid4(),
            user_role=UserRole.PROFESSOR,
        )
        with pytest.raises(ResourceNotFoundException):
            await use_case.execute(input_data)
