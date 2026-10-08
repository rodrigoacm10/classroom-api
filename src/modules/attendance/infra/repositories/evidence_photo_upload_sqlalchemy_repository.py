from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from infra.database.models.evidence_photo_upload import EvidencePhotoUploadModel
from modules.attendance.domain.entities.evidence_photo_upload import EvidencePhotoUpload
from modules.attendance.domain.repositories.evidence_photo_upload_repository import (
    EvidencePhotoUploadRepository,
)
from modules.attendance.infra.mappers.evidence_photo_upload_mapper import EvidencePhotoUploadMapper
from shared.enums.upload_status import UploadStatus


class EvidencePhotoUploadSQLAlchemyRepository(EvidencePhotoUploadRepository):

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def save(self, upload: EvidencePhotoUpload) -> EvidencePhotoUpload:
        model = EvidencePhotoUploadMapper.to_model(upload)
        merged = await self.session.merge(model)
        await self.session.flush()
        return EvidencePhotoUploadMapper.to_domain(merged)

    async def find_by_id(self, upload_id: UUID) -> EvidencePhotoUpload | None:
        stmt = select(EvidencePhotoUploadModel).where(EvidencePhotoUploadModel.id == upload_id)
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        return EvidencePhotoUploadMapper.to_domain(model) if model else None

    async def find_by_url(self, url: str) -> EvidencePhotoUpload | None:
        stmt = select(EvidencePhotoUploadModel).where(EvidencePhotoUploadModel.url == url)
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        return EvidencePhotoUploadMapper.to_domain(model) if model else None

    async def list_by_status_before(
        self, status: UploadStatus, before: datetime
    ) -> list[EvidencePhotoUpload]:
        stmt = select(EvidencePhotoUploadModel).where(
            EvidencePhotoUploadModel.status == status,
            EvidencePhotoUploadModel.uploaded_at < before,
        )
        result = await self.session.execute(stmt)
        return [EvidencePhotoUploadMapper.to_domain(m) for m in result.scalars().all()]