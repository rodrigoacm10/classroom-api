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

    def confirm(
        self,
        attendance_record_id: UUID,
        file_key: str | None = None,
        url: str | None = None,
    ) -> None:
        """
        Marca o upload como confirmado, vinculando-o ao registro de presença criado.
        Quando a foto é promovida de pending/ para confirmed/, informe a nova chave e a
        nova URL juntas, para o registro continuar apontando para o objeto que existe.
        """
        if (file_key is None) != (url is None):
            raise ValueError("file_key e url devem ser informados juntos.")

        self.status = UploadStatus.CONFIRMED
        self.confirmed_at = datetime.now(timezone.utc)
        self.attendance_record_id = attendance_record_id
        if file_key is not None and url is not None:
            self.file_key = file_key
            self.url = url

    def expire(self) -> None:
        """Marca o upload como expirado (usado pelo job de limpeza)."""
        self.status = UploadStatus.EXPIRED
