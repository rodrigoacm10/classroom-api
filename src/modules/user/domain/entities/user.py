from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4


@dataclass
class User:
    name: str
    email: str
    password_hash: str
    id: UUID = field(default_factory=uuid4)
    fcm_token: str | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
