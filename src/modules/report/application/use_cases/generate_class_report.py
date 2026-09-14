import time
from dataclasses import dataclass
from uuid import UUID

from modules.report.domain.entities.class_report import ClassReport
from modules.report.domain.services.student_calculator import get_student_compute_fn
from modules.report.infra.repositories.report_data_repository import ReportDataRepository
from modules.report.infra.repositories.report_generation_log_repository import (
    ReportGenerationLogRepository,
)
from modules.subject_class.domain.repositories.subject_class_repository import SubjectClassRepository
from modules.tenant.domain.repositories.tenant_repository import TenantRepository
from shared.exceptions import ResourceNotFoundException
from shared.parallel.compute_strategy import ComputeStrategy


@dataclass
class GenerateClassReportInput:
    tenant_id: UUID
    subject_class_id: UUID


class GenerateClassReportUseCase:
    def __init__(
        self,
        report_data_repo: ReportDataRepository,
        subject_class_repo: SubjectClassRepository,
        tenant_repo: TenantRepository,
        compute_strategy: ComputeStrategy,
        log_repo: ReportGenerationLogRepository,
    ) -> None:
        self.report_data_repo = report_data_repo
        self.subject_class_repo = subject_class_repo
        self.tenant_repo = tenant_repo
        self.compute_strategy = compute_strategy
        self.log_repo = log_repo

    async def execute(self, data: GenerateClassReportInput) -> ClassReport:
        tenant = await self.tenant_repo.find_by_id(data.tenant_id)
        if not tenant or getattr(tenant, "deleted", False):
            raise ResourceNotFoundException("Instituição/tenant não encontrada.")

        subject_class = await self.subject_class_repo.find_by_id_and_tenant(
            data.subject_class_id, data.tenant_id
        )
        if not subject_class or getattr(subject_class, "deleted", False):
            raise ResourceNotFoundException("Turma não encontrada.")

        # FASE 1 — I/O, sequencial, uma única carga em memória
        students_data = await self.report_data_repo.load_class_data(
            data.tenant_id, data.subject_class_id
        )

        # FASE 2 — CPU, paralela (estratégia injetada)
        compute_fn = get_student_compute_fn(self.compute_strategy.name)
        start = time.perf_counter()
        student_reports = self.compute_strategy.compute(students_data, compute_fn)
        duration_ms = (time.perf_counter() - start) * 1000

        # FASE 3 — Agregação final, sequencial
        total = len(student_reports)
        avg_freq = sum(r.frequency_rate for r in student_reports) / total if total else 0.0
        at_risk_count = sum(1 for r in student_reports if r.at_risk)

        await self.log_repo.create(
            tenant_id=data.tenant_id,
            subject_class_id=data.subject_class_id,
            strategy=self.compute_strategy.name,
            workers_used=self.compute_strategy.workers_used,
            items_processed=total,
            duration_ms=duration_ms,
        )

        return ClassReport(
            subject_class_id=data.subject_class_id,
            total_students=total,
            class_average_frequency=round(avg_freq, 4),
            students_at_risk=at_risk_count,
            students=sorted(student_reports, key=lambda r: r.frequency_rate),
            strategy_used=self.compute_strategy.name,
            workers_used=self.compute_strategy.workers_used,
            duration_ms=round(duration_ms, 2),
        )
