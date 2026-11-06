from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from shared.enums.record_status import RecordStatus
from shared.enums.session_status import SessionStatus


@dataclass
class StudentAttendanceHistoryItem:
    """Item do histórico de chamadas do aluno com status da sessão e de presença."""

    session_id: UUID
    subject_class_id: UUID
    subject_class_name: str
    discipline_name: str
    opened_at: datetime
    session_status: SessionStatus
    record_status: RecordStatus | None = None
    confirmed_at: datetime | None = None
    room_id: UUID | None = None
    room_name: str | None = None
    record_id: UUID | None = None
