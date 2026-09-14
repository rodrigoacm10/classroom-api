from dataclasses import dataclass
from uuid import UUID


@dataclass
class StudentReport:
    tenant_member_id: UUID
    student_name: str
    total_present: int
    total_absent: int
    total_irregular: int
    frequency_rate: float          # 0.0 a 1.0
    at_risk: bool                  # frequency_rate < limite institucional (padrão 0.75)
    avg_distance_meters: float     # métrica geoespacial recalculada
    confirmations_near_limit: int  # nº de confirmações a ≥90% do raio de tolerância
