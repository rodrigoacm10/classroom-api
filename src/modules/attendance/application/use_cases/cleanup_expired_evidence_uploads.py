from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from infra.storage.storage_service import StorageService
from modules.attendance.domain.repositories.evidence_photo_upload_repository import (
    EvidencePhotoUploadRepository,
)
from shared.enums.upload_status import UploadStatus


@dataclass
class CleanupExpiredEvidenceUploadsInput:
    ttl_minutes: int


@dataclass
class CleanupExpiredEvidenceUploadsOutput:
    expired_count: int
    failed_count: int


class CleanupExpiredEvidenceUploadsUseCase:
    """
    Apaga do storage as fotos de evidência que ficaram `pending` além do TTL
    (upload feito, mas a confirmação de presença nunca aconteceu) e marca
    o registro como `expired`.
    """

    def __init__(
        self,
        upload_repo: EvidencePhotoUploadRepository,
        storage_service: StorageService,
    ) -> None:
        self.upload_repo = upload_repo
        self.storage_service = storage_service

    async def execute(
        self, data: CleanupExpiredEvidenceUploadsInput
    ) -> CleanupExpiredEvidenceUploadsOutput:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=data.ttl_minutes)
        stale_uploads = await self.upload_repo.list_by_status_before(UploadStatus.PENDING, cutoff)

        expired_count = 0
        failed_count = 0

        for upload in stale_uploads:
            # Primeiro o storage, depois o banco: se o delete falhar, o registro
            # continua `pending` e a próxima execução tenta de novo. Se o delete
            # funcionar e o update falhar, a próxima execução apaga de novo, o que
            # é seguro porque delete_object é idempotente.
            try:
                await self.storage_service.delete(upload.file_key)
            except Exception:
                failed_count += 1
                continue

            upload.expire()
            await self.upload_repo.save(upload)
            expired_count += 1

        return CleanupExpiredEvidenceUploadsOutput(
            expired_count=expired_count,
            failed_count=failed_count,
        )
