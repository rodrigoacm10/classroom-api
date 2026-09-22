from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID, uuid4


@dataclass
class SubjectClass:
    tenant_id: UUID
    name: str
    discipline_name: str
    professor_id: UUID | None = None
    room_id: UUID | None = None
    deleted: bool = False
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
