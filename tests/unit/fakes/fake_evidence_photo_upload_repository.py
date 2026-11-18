from datetime import datetime
from uuid import UUID

from modules.attendance.domain.entities.evidence_photo_upload import EvidencePhotoUpload
from modules.attendance.domain.repositories.evidence_photo_upload_repository import (
    EvidencePhotoUploadRepository,
)
from shared.enums.upload_status import UploadStatus


class FakeEvidencePhotoUploadRepository(EvidencePhotoUploadRepository):

    def __init__(self) -> None:
        self.uploads: dict[UUID, EvidencePhotoUpload] = {}

    async def save(self, upload: EvidencePhotoUpload) -> EvidencePhotoUpload:
        self.uploads[upload.id] = upload
        return upload

    async def find_by_id(self, upload_id: UUID) -> EvidencePhotoUpload | None:
        return self.uploads.get(upload_id)

    async def find_by_url(self, url: str) -> EvidencePhotoUpload | None:
        for upload in self.uploads.values():
            if upload.url == url:
                return upload
        return None

    async def list_by_status_before(
        self, status: UploadStatus, before: datetime
    ) -> list[EvidencePhotoUpload]:
        return [
            u for u in self.uploads.values()
            if u.status == status and u.uploaded_at < before
        ]