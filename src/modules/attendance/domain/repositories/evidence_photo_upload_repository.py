from datetime import datetime
from typing import Protocol
from uuid import UUID

from modules.attendance.domain.entities.evidence_photo_upload import EvidencePhotoUpload
from shared.enums.upload_status import UploadStatus


class EvidencePhotoUploadRepository(Protocol):

    async def save(self, upload: EvidencePhotoUpload) -> EvidencePhotoUpload: ...

    async def find_by_id(self, upload_id: UUID) -> EvidencePhotoUpload | None: ...

    async def find_by_url(self, url: str) -> EvidencePhotoUpload | None: ...

    async def list_by_status_before(
        self, status: UploadStatus, before: datetime
    ) -> list[EvidencePhotoUpload]: ...