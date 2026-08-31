from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from infra.database.session import get_db
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
from modules.enrollment.infra.repositories.enrollment_sqlalchemy_repository import (
    EnrollmentSQLAlchemyRepository,
)
from modules.enrollment.interface.schemas.enrollment_schemas import (
    EnrollStudentRequest,
    EnrollmentResponse,
)
from modules.subject_class.infra.repositories.subject_class_sqlalchemy_repository import (
    SubjectClassSQLAlchemyRepository,
)
from modules.tenant.infra.repositories.tenant_member_sqlalchemy_repository import (
    TenantMemberSQLAlchemyRepository,
)
from security.dependencies.require_role import require_role
from shared.enums.enrollment_status import EnrollmentStatus
from shared.enums.user_role import UserRole

from modules.enrollment.application.use_cases.get_enrollment import (
    GetEnrollmentInput,
    GetEnrollmentUseCase,
)
from modules.enrollment.application.use_cases.list_enrollments_by_member import (
    ListEnrollmentsByMemberInput,
    ListEnrollmentsByMemberUseCase,
)

router = APIRouter(
    prefix="/tenants/{tenant_id}/subject-classes/{subject_class_id}/enrollments",
    tags=["enrollments"],
)

member_enrollments_router = APIRouter(
    prefix="/tenants/{tenant_id}/members/{member_id}/enrollments",
    tags=["enrollments"],
)


@router.post(
    "",
    response_model=EnrollmentResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role(UserRole.ADMIN, UserRole.PROFESSOR))],
)
async def enroll_student(
    tenant_id: UUID,
    subject_class_id: UUID,
    body: EnrollStudentRequest,
    db: AsyncSession = Depends(get_db),
) -> EnrollmentResponse:
    """Matricula um aluno (TenantMember com papel ALUNO) em uma turma."""
    enrollment_repo = EnrollmentSQLAlchemyRepository(session=db)
    subject_class_repo = SubjectClassSQLAlchemyRepository(session=db)
    member_repo = TenantMemberSQLAlchemyRepository(session=db)
    use_case = EnrollStudentUseCase(
        enrollment_repo=enrollment_repo,
        subject_class_repo=subject_class_repo,
        member_repo=member_repo,
    )
    enrollment = await use_case.execute(
        EnrollStudentInput(
            subject_class_id=subject_class_id,
            tenant_member_id=body.tenant_member_id,
            tenant_id=tenant_id,
        )
    )
    return EnrollmentResponse.model_validate(enrollment)


@router.get("", response_model=list[EnrollmentResponse])
async def list_enrollments(
    tenant_id: UUID,
    subject_class_id: UUID,
    status: EnrollmentStatus | None = None,
    include_deleted: bool = False,
    db: AsyncSession = Depends(get_db),
) -> list[EnrollmentResponse]:
    """Lista matriculados da turma. Filtrável por status. ADMIN pode incluir deletados."""
    enrollment_repo = EnrollmentSQLAlchemyRepository(session=db)
    subject_class_repo = SubjectClassSQLAlchemyRepository(session=db)
    use_case = ListEnrollmentsUseCase(
        enrollment_repo=enrollment_repo,
        subject_class_repo=subject_class_repo,
    )
    enrollments = await use_case.execute(
        ListEnrollmentsInput(
            subject_class_id=subject_class_id,
            tenant_id=tenant_id,
            status=status,
            include_deleted=include_deleted,
        )
    )
    return [EnrollmentResponse.model_validate(e) for e in enrollments]


@router.get("/{enrollment_id}", response_model=EnrollmentResponse)
async def get_enrollment(
    tenant_id: UUID,
    subject_class_id: UUID,
    enrollment_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> EnrollmentResponse:
    """Retorna uma matrícula específica pelo ID."""
    enrollment_repo = EnrollmentSQLAlchemyRepository(session=db)
    use_case = GetEnrollmentUseCase(enrollment_repo=enrollment_repo)
    enrollment = await use_case.execute(
        GetEnrollmentInput(
            enrollment_id=enrollment_id,
            subject_class_id=subject_class_id,
        )
    )
    return EnrollmentResponse.model_validate(enrollment)


@member_enrollments_router.get("", response_model=list[EnrollmentResponse])
async def list_enrollments_by_member(
    tenant_id: UUID,
    member_id: UUID,
    status: EnrollmentStatus | None = None,
    include_deleted: bool = False,
    db: AsyncSession = Depends(get_db),
) -> list[EnrollmentResponse]:
    """Lista todas as turmas em que um aluno está matriculado na instituição."""
    enrollment_repo = EnrollmentSQLAlchemyRepository(session=db)
    member_repo = TenantMemberSQLAlchemyRepository(session=db)
    use_case = ListEnrollmentsByMemberUseCase(
        enrollment_repo=enrollment_repo,
        member_repo=member_repo,
    )
    enrollments = await use_case.execute(
        ListEnrollmentsByMemberInput(
            tenant_id=tenant_id,
            tenant_member_id=member_id,
            status=status,
            include_deleted=include_deleted,
        )
    )
    return [EnrollmentResponse.model_validate(e) for e in enrollments]


@router.patch(
    "/{enrollment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_role(UserRole.ADMIN))],
)
async def drop_enrollment(
    tenant_id: UUID,
    subject_class_id: UUID,
    enrollment_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Cancela matrícula por evento legítimo (status → dropped). Histórico preservado. Apenas ADMIN."""
    enrollment_repo = EnrollmentSQLAlchemyRepository(session=db)
    use_case = DropEnrollmentUseCase(enrollment_repo=enrollment_repo)
    await use_case.execute(
        DropEnrollmentInput(
            enrollment_id=enrollment_id,
            subject_class_id=subject_class_id,
        )
    )


@router.delete(
    "/{enrollment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_role(UserRole.ADMIN))],
)
async def delete_enrollment(
    tenant_id: UUID,
    subject_class_id: UUID,
    enrollment_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Remove matrícula por erro administrativo (soft delete → deleted=True). Some do histórico. Apenas ADMIN."""
    enrollment_repo = EnrollmentSQLAlchemyRepository(session=db)
    use_case = DeleteEnrollmentUseCase(enrollment_repo=enrollment_repo)
    await use_case.execute(
        DeleteEnrollmentInput(
            enrollment_id=enrollment_id,
            subject_class_id=subject_class_id,
        )
    )
