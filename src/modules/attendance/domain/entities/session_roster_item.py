from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from shared.enums.record_status import RecordStatus


@dataclass
class SessionRosterItem:
    """Aluno matriculado na turma, com o record da chamada quando existir."""

    tenant_member_id: UUID
    student_name: str
    enrollment_id: UUID
    record_id: UUID | None
    confirmed_at: datetime | None
    distance_meters: float | None
    within_radius: bool | None
    record_status: RecordStatus | None
