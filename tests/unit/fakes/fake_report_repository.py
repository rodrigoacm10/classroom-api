from uuid import UUID

from modules.report.domain.entities.student_attendance_data import StudentAttendanceData


class FakeReportDataRepository:
    """Repositório em memória para testes unitários do use case de relatório."""

    def __init__(self) -> None:
        self.data: list[StudentAttendanceData] = []

    async def load_class_data(
        self, tenant_id: UUID, subject_class_id: UUID
    ) -> list[StudentAttendanceData]:
        return list(self.data)


class FakeReportGenerationLogRepository:
    """Captura logs de execução sem persistir em banco."""

    def __init__(self) -> None:
        self.logs: list[dict] = []

    async def create(
        self,
        tenant_id: UUID,
        subject_class_id: UUID,
        strategy: str,
        workers_used: int,
        items_processed: int,
        duration_ms: float,
    ) -> None:
        self.logs.append(
            {
                "tenant_id": tenant_id,
                "subject_class_id": subject_class_id,
                "strategy": strategy,
                "workers_used": workers_used,
                "items_processed": items_processed,
                "duration_ms": duration_ms,
            }
        )
