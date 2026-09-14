from dataclasses import dataclass, field
from uuid import UUID


@dataclass
class RawConfirmation:
    """Dado mínimo de uma confirmação — só o necessário para o cálculo."""
    latitude: float
    longitude: float
    record_status: str  # "regular" | "irregular" | "approved" | "rejected"


@dataclass
class StudentAttendanceData:
    """
    Entrada para a Fase 2 (cálculo). Contém apenas tipos primitivos/dataclasses
    simples — obrigatório para ser serializável entre processos (pickle).
    NUNCA deve conter uma sessão SQLAlchemy ou qualquer objeto de infraestrutura.
    """
    tenant_member_id: UUID
    student_name: str
    total_sessions: int
    confirmations: list[RawConfirmation] = field(default_factory=list)
    room_lat: float = 0.0
    room_lon: float = 0.0
    tolerance_radius_meters: float = 50.0
