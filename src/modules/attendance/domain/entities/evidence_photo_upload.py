from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID, uuid4

from shared.enums.upload_status import UploadStatus


@dataclass
class EvidencePhotoUpload:
    session_id: UUID
    file_key: str
    url: str
    status: UploadStatus = UploadStatus.PENDING
    confirmed_at: datetime | None = None
    attendance_record_id: UUID | None = None
    uploaded_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    id: UUID = field(default_factory=uuid4)

    def confirm(self, attendance_record_id: UUID) -> None:
        """Marca o upload como confirmado, vinculando-o ao registro de presença criado."""
        self.status = UploadStatus.CONFIRMED
        self.confirmed_at = datetime.now(timezone.utc)
        self.attendance_record_id = attendance_record_id

    def expire(self) -> None:
        """Marca o upload como expirado (usado pelo job de limpeza, Ponto 2)."""
        self.status = UploadStatus.EXPIRED