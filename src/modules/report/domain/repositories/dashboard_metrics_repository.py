from typing import Protocol
from uuid import UUID

from modules.report.domain.entities.dashboard_metrics import DashboardMetrics


class DashboardMetricsRepository(Protocol):
    async def get_metrics(
        self,
        tenant_id: UUID,
        professor_user_id: UUID | None = None,
        active: bool | None = None,
    ) -> DashboardMetrics: ...
