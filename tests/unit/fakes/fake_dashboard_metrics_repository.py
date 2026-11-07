from typing import Any
from uuid import UUID

from modules.report.domain.entities.dashboard_metrics import DashboardMetrics


class FakeDashboardMetricsRepository:
    def __init__(self) -> None:
        self.metrics_to_return: DashboardMetrics | None = None
        self.calls: list[dict[str, Any]] = []

    def set_metrics(self, metrics: DashboardMetrics) -> None:
        self.metrics_to_return = metrics

    async def get_metrics(
        self,
        tenant_id: UUID,
        professor_user_id: UUID | None = None,
        active: bool | None = None,
    ) -> DashboardMetrics:
        self.calls.append(
            {
                "tenant_id": tenant_id,
                "professor_user_id": professor_user_id,
                "active": active,
            }
        )
        if self.metrics_to_return is not None:
            return self.metrics_to_return
        return DashboardMetrics(
            total_classes=0,
            total_unique_students=0,
            average_attendance_rate=0.0,
            total_students_at_risk=0,
            week_frequency=[],
            at_risk_students=[],
        )
