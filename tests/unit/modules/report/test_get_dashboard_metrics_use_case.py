from uuid import uuid4

import pytest

from modules.report.application.use_cases.get_dashboard_metrics import (
    GetDashboardMetricsInput,
    GetDashboardMetricsUseCase,
)
from modules.report.domain.entities.dashboard_metrics import DashboardMetrics
from shared.enums.user_role import UserRole
from shared.exceptions import ForbiddenException, ResourceNotFoundException
from tests.factories.tenant_factory import TenantFactory
from tests.unit.fakes.fake_dashboard_metrics_repository import FakeDashboardMetricsRepository
from tests.unit.fakes.fake_tenant_repository import FakeTenantRepository


@pytest.mark.asyncio
class TestGetDashboardMetricsUseCase:
    async def test_professor_scopes_metrics_to_own_user_id(self) -> None:
        """Deve repassar o professor_user_id para o repositório quando o papel for PROFESSOR."""
        tenant_repo = FakeTenantRepository()
        metrics_repo = FakeDashboardMetricsRepository()
        tenant = TenantFactory.make()
        tenant_repo.seed(tenant)

        expected_metrics = DashboardMetrics(
            total_classes=4,
            total_unique_students=85,
            average_attendance_rate=0.92,
            total_students_at_risk=7,
        )
        metrics_repo.set_metrics(expected_metrics)

        prof_user_id = uuid4()
        use_case = GetDashboardMetricsUseCase(metrics_repo=metrics_repo, tenant_repo=tenant_repo)

        result = await use_case.execute(
            GetDashboardMetricsInput(
                tenant_id=tenant.id,
                user_id=prof_user_id,
                user_role=UserRole.PROFESSOR,
                active=True,
            )
        )

        assert result == expected_metrics
        assert len(metrics_repo.calls) == 1
        assert metrics_repo.calls[0]["tenant_id"] == tenant.id
        assert metrics_repo.calls[0]["professor_user_id"] == prof_user_id
        assert metrics_repo.calls[0]["active"] is True

    async def test_admin_and_coordenador_do_not_scope_to_professor(self) -> None:
        """Deve passar professor_user_id como None para papéis ADMIN e COORDENADOR, abrangendo todo o tenant."""
        tenant_repo = FakeTenantRepository()
        metrics_repo = FakeDashboardMetricsRepository()
        tenant = TenantFactory.make()
        tenant_repo.seed(tenant)

        use_case = GetDashboardMetricsUseCase(metrics_repo=metrics_repo, tenant_repo=tenant_repo)

        # Teste com ADMIN
        await use_case.execute(
            GetDashboardMetricsInput(
                tenant_id=tenant.id,
                user_id=uuid4(),
                user_role=UserRole.ADMIN,
                active=True,
            )
        )
        assert metrics_repo.calls[-1]["professor_user_id"] is None

        # Teste com COORDENADOR
        await use_case.execute(
            GetDashboardMetricsInput(
                tenant_id=tenant.id,
                user_id=uuid4(),
                user_role=UserRole.COORDENADOR,
                active=None,
            )
        )
        assert metrics_repo.calls[-1]["professor_user_id"] is None

    async def test_student_role_raises_forbidden(self) -> None:
        """Deve lançar ForbiddenException quando o papel for ALUNO."""
        tenant_repo = FakeTenantRepository()
        metrics_repo = FakeDashboardMetricsRepository()
        tenant = TenantFactory.make()
        tenant_repo.seed(tenant)

        use_case = GetDashboardMetricsUseCase(metrics_repo=metrics_repo, tenant_repo=tenant_repo)

        with pytest.raises(ForbiddenException):
            await use_case.execute(
                GetDashboardMetricsInput(
                    tenant_id=tenant.id,
                    user_id=uuid4(),
                    user_role=UserRole.ALUNO,
                )
            )

    async def test_none_role_raises_forbidden(self) -> None:
        """Deve lançar ForbiddenException quando o papel do usuário for None."""
        tenant_repo = FakeTenantRepository()
        metrics_repo = FakeDashboardMetricsRepository()
        tenant = TenantFactory.make()
        tenant_repo.seed(tenant)

        use_case = GetDashboardMetricsUseCase(metrics_repo=metrics_repo, tenant_repo=tenant_repo)

        with pytest.raises(ForbiddenException):
            await use_case.execute(
                GetDashboardMetricsInput(
                    tenant_id=tenant.id,
                    user_id=uuid4(),
                    user_role=None,
                )
            )

    async def test_tenant_not_found_raises_not_found(self) -> None:
        """Deve lançar ResourceNotFoundException quando o tenant não for encontrado ou estiver deletado."""
        tenant_repo = FakeTenantRepository()
        metrics_repo = FakeDashboardMetricsRepository()
        use_case = GetDashboardMetricsUseCase(metrics_repo=metrics_repo, tenant_repo=tenant_repo)

        with pytest.raises(ResourceNotFoundException):
            await use_case.execute(
                GetDashboardMetricsInput(
                    tenant_id=uuid4(),
                    user_id=uuid4(),
                    user_role=UserRole.PROFESSOR,
                )
            )

    async def test_active_filter_is_passed_to_repository(self) -> None:
        """Deve repassar corretamente o filtro active (True, False ou None) para o repositório."""
        tenant_repo = FakeTenantRepository()
        metrics_repo = FakeDashboardMetricsRepository()
        tenant = TenantFactory.make()
        tenant_repo.seed(tenant)

        use_case = GetDashboardMetricsUseCase(metrics_repo=metrics_repo, tenant_repo=tenant_repo)

        for active_val in (True, False, None):
            await use_case.execute(
                GetDashboardMetricsInput(
                    tenant_id=tenant.id,
                    user_id=uuid4(),
                    user_role=UserRole.ADMIN,
                    active=active_val,
                )
            )
            assert metrics_repo.calls[-1]["active"] is active_val
