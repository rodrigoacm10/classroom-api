from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID, uuid4

from shared.enums.session_status import SessionStatus


@dataclass
class SubjectClassInfo:
    id: UUID
    name: str
    discipline_name: str


@dataclass
class RoomInfo:
    id: UUID
    name: str


@dataclass
class AttendanceSession:
    subject_class_id: UUID
    day_code: str
    expires_at: datetime
    room_id: UUID | None = None
    subject_class: SubjectClassInfo | None = None
    room: RoomInfo | None = None
    opened_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    closed_at: datetime | None = None
    status: SessionStatus = SessionStatus.OPEN
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def is_open(self) -> bool:
        return self.status == SessionStatus.OPEN

    @property
    def is_expired(self) -> bool:
        now = datetime.now(timezone.utc)
        expires_at_utc = (
            self.expires_at if self.expires_at.tzinfo else self.expires_at.replace(tzinfo=timezone.utc)
        )
        return now >= expires_at_utc

    def close(self) -> None:
        self.status = SessionStatus.CLOSED
        self.closed_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)
