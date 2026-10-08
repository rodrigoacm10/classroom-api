from dataclasses import dataclass
from uuid import UUID

from infra.storage.evidence_photo_service import upload_evidence_photo
from infra.storage.storage_service import StorageService
from modules.attendance.domain.entities.evidence_photo_upload import EvidencePhotoUpload
from modules.attendance.domain.repositories.attendance_session_repository import AttendanceSessionRepository
from modules.attendance.domain.repositories.evidence_photo_upload_repository import (
    EvidencePhotoUploadRepository,
)
from shared.enums.session_status import SessionStatus
from shared.exceptions import BusinessRuleException, ResourceNotFoundException


@dataclass
class UploadEvidencePhotoInput:
    tenant_id: UUID
    subject_class_id: UUID
    session_id: UUID
    file_bytes: bytes
    content_type: str


@dataclass
class UploadEvidencePhotoOutput:
    url: str


class UploadEvidencePhotoUseCase:

    def __init__(
        self,
        session_repo: AttendanceSessionRepository,
        upload_repo: EvidencePhotoUploadRepository,
        storage_service: StorageService,
    ) -> None:
        self.session_repo = session_repo
        self.upload_repo = upload_repo
        self.storage_service = storage_service

    async def execute(self, data: UploadEvidencePhotoInput) -> UploadEvidencePhotoOutput:
        session = await self.session_repo.find_by_id_and_class(data.session_id, data.subject_class_id)
        if not session:
            raise ResourceNotFoundException("Sessão de chamada não encontrada.")

        if session.status != SessionStatus.OPEN:
            raise BusinessRuleException("A chamada não está aberta para receber evidências.")

        uploaded = await upload_evidence_photo(
            storage_service=self.storage_service,
            session_id=data.session_id,
            file_bytes=data.file_bytes,
            content_type=data.content_type,
        )

        await self.upload_repo.save(
            EvidencePhotoUpload(
                session_id=data.session_id,
                file_key=uploaded.key,
                url=uploaded.url,
            )
        )

        return UploadEvidencePhotoOutput(url=uploaded.url)