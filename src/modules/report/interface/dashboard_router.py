from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from infra.database.session import get_db
from modules.report.application.use_cases.get_dashboard_metrics import (
    GetDashboardMetricsInput,
    GetDashboardMetricsUseCase,
)
from modules.report.infra.repositories.dashboard_metrics_sqlalchemy_repository import (
    DashboardMetricsSQLAlchemyRepository,
)
from modules.report.interface.schemas.dashboard_schemas import DashboardMetricsResponse
from modules.tenant.infra.repositories.tenant_sqlalchemy_repository import (
    TenantSQLAlchemyRepository,
)
from security.dependencies.current_user import AuthContext, get_auth_context, get_current_tenant_id
from security.dependencies.require_role import require_role
from shared.enums.user_role import UserRole

router = APIRouter(
    prefix="/dashboard",
    tags=["dashboard"],
)


@router.get(
    "/metrics",
    response_model=DashboardMetricsResponse,
    dependencies=[Depends(require_role(UserRole.ADMIN, UserRole.COORDENADOR, UserRole.PROFESSOR))],
)
async def get_dashboard_metrics(
    active: bool | None = Query(
        None,
        description="Filtrar métricas por turmas ativas (true), inativas (false) ou todas se omitido.",
    ),
    tenant_id: UUID = Depends(get_current_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
) -> DashboardMetricsResponse:
    """Retorna métricas consolidadas (total de turmas, alunos únicos e frequência média dos últimos 30 dias)."""
    metrics_repo = DashboardMetricsSQLAlchemyRepository(session=db)
    tenant_repo = TenantSQLAlchemyRepository(session=db)

    use_case = GetDashboardMetricsUseCase(
        metrics_repo=metrics_repo,
        tenant_repo=tenant_repo,
    )

    metrics = await use_case.execute(
        GetDashboardMetricsInput(
            tenant_id=tenant_id,
            user_id=auth.user.id,
            user_role=auth.role,
            active=active,
        )
    )

    return DashboardMetricsResponse.model_validate(metrics)
