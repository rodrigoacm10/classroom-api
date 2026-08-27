from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID, uuid4

from shared.enums.user_role import UserRole


@dataclass
class TenantMember:
    tenant_id: UUID
    user_id: UUID
    role: UserRole
    id: UUID = field(default_factory=uuid4)
    deleted: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
