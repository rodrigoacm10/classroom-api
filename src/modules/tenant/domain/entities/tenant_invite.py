import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID, uuid4

from shared.enums.user_role import UserRole


@dataclass
class TenantInvite:
    tenant_id: UUID
    email: str
    role: UserRole
    expires_at: datetime
    invited_by: UUID | None = None
    token: str = field(default_factory=lambda: secrets.token_urlsafe(32))
    accepted_at: datetime | None = None
    revoked_at: datetime | None = None
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def is_expired(self) -> bool:
        # Garante comparação segura com fuso horário
        now = datetime.now(timezone.utc)
        exp = self.expires_at if self.expires_at.tzinfo else self.expires_at.replace(tzinfo=timezone.utc)
        return now > exp

    @property
    def is_accepted(self) -> bool:
        return self.accepted_at is not None

    @property
    def is_revoked(self) -> bool:
        return self.revoked_at is not None

    @property
    def is_pending(self) -> bool:
        return not self.is_accepted and not self.is_revoked and not self.is_expired
