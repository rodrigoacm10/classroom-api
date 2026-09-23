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
    total_students: int = 0
    confirmed_count: int = 0
    irregular_count: int = 0

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

    def cancel(self) -> None:
        self.status = SessionStatus.CANCELLED
        self.closed_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)
