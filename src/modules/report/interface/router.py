from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from infra.database.session import get_db
from modules.report.application.use_cases.generate_class_report import (
    GenerateClassReportInput,
    GenerateClassReportUseCase,
)
from modules.report.application.use_cases.get_student_report import (
    GetStudentReportInput,
    GetStudentReportUseCase,
)
from modules.report.infra.repositories.report_data_repository import ReportDataRepository
from modules.report.infra.repositories.report_generation_log_repository import (
    ReportGenerationLogRepository,
)
from modules.report.infra.strategy_factory import get_report_compute_strategy
from modules.report.interface.schemas.report_schemas import (
    ClassReportResponse,
    StudentReportResponse,
)
from modules.subject_class.infra.repositories.subject_class_sqlalchemy_repository import (
    SubjectClassSQLAlchemyRepository,
)
from modules.tenant.infra.repositories.tenant_sqlalchemy_repository import (
    TenantSQLAlchemyRepository,
)
from security.dependencies.current_user import get_current_tenant_id
from security.dependencies.require_role import require_role
from shared.enums.user_role import UserRole

router = APIRouter(
    prefix="/subject-classes/{subject_class_id}/reports",
    tags=["reports"],
)


@router.post(
    "/frequency",
    response_model=ClassReportResponse,
    dependencies=[Depends(require_role(UserRole.ADMIN, UserRole.PROFESSOR))],
)
async def generate_frequency_report(
    subject_class_id: UUID,
    tenant_id: UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
) -> ClassReportResponse:
    """Gera o relatório de frequência da turma, com métricas geoespaciais recalculadas em paralelo."""
    use_case = GenerateClassReportUseCase(
        report_data_repo=ReportDataRepository(session=db),
        subject_class_repo=SubjectClassSQLAlchemyRepository(session=db),
        tenant_repo=TenantSQLAlchemyRepository(session=db),
        compute_strategy=get_report_compute_strategy(),
        log_repo=ReportGenerationLogRepository(session=db),
    )
    report = await use_case.execute(
        GenerateClassReportInput(tenant_id=tenant_id, subject_class_id=subject_class_id)
    )
    return ClassReportResponse.model_validate(report)


@router.get(
    "/frequency/{tenant_member_id}",
    response_model=StudentReportResponse,
    dependencies=[Depends(require_role(UserRole.ADMIN, UserRole.PROFESSOR))],
)
async def get_student_frequency_report(
    subject_class_id: UUID,
    tenant_member_id: UUID,
    tenant_id: UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
) -> StudentReportResponse:
    """Retorna o detalhe do relatório de frequência de um aluno específico da turma."""
    use_case = GetStudentReportUseCase(
        report_data_repo=ReportDataRepository(session=db),
        subject_class_repo=SubjectClassSQLAlchemyRepository(session=db),
        tenant_repo=TenantSQLAlchemyRepository(session=db),
    )
    report = await use_case.execute(
        GetStudentReportInput(
            tenant_id=tenant_id,
            subject_class_id=subject_class_id,
            tenant_member_id=tenant_member_id,
        )
    )
    return StudentReportResponse.model_validate(report)
