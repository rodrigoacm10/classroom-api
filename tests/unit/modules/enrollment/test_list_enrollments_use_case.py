from uuid import uuid4

import pytest

from modules.enrollment.application.use_cases.list_enrollments import (
    ListEnrollmentsInput,
    ListEnrollmentsUseCase,
)
from modules.enrollment.domain.entities.enrollment import Enrollment
from modules.subject_class.domain.entities.subject_class import SubjectClass
from shared.enums.enrollment_status import EnrollmentStatus
from shared.exceptions import ResourceNotFoundException
from shared.pagination import PaginationParams
from tests.factories.tenant_factory import TenantFactory
from tests.unit.fakes.fake_enrollment_repository import FakeEnrollmentRepository
from tests.unit.fakes.fake_subject_class_repository import FakeSubjectClassRepository


@pytest.mark.asyncio
class TestListEnrollmentsUseCase:

    async def test_list_enrollments_paginated_success(self):
        """Deve listar matrículas da turma com paginação offset e status."""
        enrollment_repo = FakeEnrollmentRepository()
        subject_class_repo = FakeSubjectClassRepository()

        tenant = TenantFactory.make()
        sc = SubjectClass(tenant_id=tenant.id, name="Cálculo I", discipline_name="Matemática")
        await subject_class_repo.save(sc)

        m1_id = uuid4()
        m2_id = uuid4()
        e1 = Enrollment(subject_class_id=sc.id, tenant_member_id=m1_id, status=EnrollmentStatus.ACTIVE)
        e2 = Enrollment(subject_class_id=sc.id, tenant_member_id=m2_id, status=EnrollmentStatus.DROPPED)
        await enrollment_repo.save(e1)
        await enrollment_repo.save(e2)

        use_case = ListEnrollmentsUseCase(
            enrollment_repo=enrollment_repo,
            subject_class_repo=subject_class_repo,
        )

        page_all = await use_case.execute(
            ListEnrollmentsInput(
                subject_class_id=sc.id,
                tenant_id=tenant.id,
                pagination=PaginationParams(page=1, page_size=10),
            )
        )
        assert page_all.total == 2
        assert len(page_all.items) == 2

        page_active = await use_case.execute(
            ListEnrollmentsInput(
                subject_class_id=sc.id,
                tenant_id=tenant.id,
                status=EnrollmentStatus.ACTIVE,
            )
        )
        assert page_active.total == 1
        assert page_active.items[0].tenant_member_id == m1_id

    async def test_list_enrollments_not_found(self):
        """Deve lançar ResourceNotFoundException caso a turma não exista."""
        enrollment_repo = FakeEnrollmentRepository()
        subject_class_repo = FakeSubjectClassRepository()
        use_case = ListEnrollmentsUseCase(
            enrollment_repo=enrollment_repo,
            subject_class_repo=subject_class_repo,
        )

        with pytest.raises(ResourceNotFoundException, match="Turma não encontrada."):
            await use_case.execute(
                ListEnrollmentsInput(
                    subject_class_id=uuid4(),
                    tenant_id=uuid4(),
                )
            )
