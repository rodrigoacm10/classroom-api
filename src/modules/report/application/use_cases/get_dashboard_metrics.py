from dataclasses import dataclass
from uuid import UUID

from modules.report.domain.entities.dashboard_metrics import DashboardMetrics
from modules.report.domain.repositories.dashboard_metrics_repository import (
    DashboardMetricsRepository,
)
from modules.tenant.domain.repositories.tenant_repository import TenantRepository
from shared.enums.user_role import UserRole
from shared.exceptions import ForbiddenException, ResourceNotFoundException


@dataclass
class GetDashboardMetricsInput:
    tenant_id: UUID
    user_id: UUID
    user_role: UserRole | None = None
    active: bool | None = None


class GetDashboardMetricsUseCase:
    def __init__(
        self,
        metrics_repo: DashboardMetricsRepository,
        tenant_repo: TenantRepository,
    ) -> None:
        self.metrics_repo = metrics_repo
        self.tenant_repo = tenant_repo

    async def execute(self, data: GetDashboardMetricsInput) -> DashboardMetrics:
        tenant = await self.tenant_repo.find_by_id(data.tenant_id)
        if not tenant or getattr(tenant, "deleted", False):
            raise ResourceNotFoundException("Instituição/tenant não encontrada.")

        if data.user_role not in (UserRole.ADMIN, UserRole.COORDENADOR, UserRole.PROFESSOR):
            raise ForbiddenException(
                "Apenas administradores, coordenadores e professores podem consultar as métricas do dashboard."
            )

        professor_user_id = data.user_id if data.user_role == UserRole.PROFESSOR else None

        return await self.metrics_repo.get_metrics(
            tenant_id=data.tenant_id,
            professor_user_id=professor_user_id,
            active=data.active,
        )
