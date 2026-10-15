from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class StudentMetrics:
    """Read-model consolidado de indicadores do aluno no tenant ativo."""

    total_classes: int
    average_attendance_rate: float
    at_risk_count: int
