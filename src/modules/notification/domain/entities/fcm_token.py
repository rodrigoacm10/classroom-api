from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID, uuid4


@dataclass
class FCMToken:
    user_id: UUID
    device_id: str
    fcm_token: str
    platform: str
    app_version: str | None = None
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    id: UUID = field(default_factory=uuid4)
