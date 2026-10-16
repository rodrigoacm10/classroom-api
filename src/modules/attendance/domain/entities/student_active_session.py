from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from shared.enums.record_status import RecordStatus


@dataclass
class StudentActiveSession:
    """Sessão de chamada aberta para o aluno matriculado."""

    session_id: UUID
    subject_class_id: UUID
    subject_class_name: str
    discipline_name: str
    opened_at: datetime
    expires_at: datetime
    already_confirmed: bool
    room_id: UUID | None = None
    room_name: str | None = None
    record_id: UUID | None = None
    record_status: RecordStatus | None = None

    @property
    def duration_minutes(self) -> int:
        opened = self.opened_at
        expires = self.expires_at
        if opened.tzinfo is None:
            opened = opened.replace(tzinfo=timezone.utc)
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        seconds = (expires - opened).total_seconds()
        return max(int(round(seconds / 60)), 0)
