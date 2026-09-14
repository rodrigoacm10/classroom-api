from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from infra.database.models.report_generation_log import ReportGenerationLogModel


class ReportGenerationLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        tenant_id: UUID,
        subject_class_id: UUID,
        strategy: str,
        workers_used: int,
        items_processed: int,
        duration_ms: float,
    ) -> None:
        model = ReportGenerationLogModel(
            tenant_id=tenant_id,
            subject_class_id=subject_class_id,
            strategy=strategy,
            workers_used=workers_used,
            items_processed=items_processed,
            duration_ms=duration_ms,
        )
        self.session.add(model)
        await self.session.flush()
