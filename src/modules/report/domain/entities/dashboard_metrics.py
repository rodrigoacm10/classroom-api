from dataclasses import dataclass, field
from uuid import UUID


@dataclass
class DayAttendanceMetric:
    """Métrica de frequência diária para um dia da semana (Domingo a Sábado)."""

    date: str
    day_of_week: int  # 0 (DOM) a 6 (SAB)
    day_label: str  # "DOM", "SEG", "TER", "QUA", "QUI", "SEX", "SAB"
    attendance_rate: float  # 0.0 a 1.0
    total_sessions: int
    total_expected: int
    total_presents: int


@dataclass
class AtRiskStudentMetric:
    """Resumo de uma matrícula em risco de reprovação por falta (< 75%)."""

    enrollment_id: UUID
    student_name: str
    class_name: str
    total_sessions: int
    absences: int
    attendance_rate: float  # 0.0 a 1.0
    critical: bool  # True se <= 71% (danger zone), False se 72-74% (warning zone)


@dataclass
class DashboardMetrics:
    """Métricas consolidadas para os cards do topo do dashboard, gráfico semanal e alunos em risco."""

    total_classes: int
    total_unique_students: int
    average_attendance_rate: float
    total_students_at_risk: int
    week_frequency: list[DayAttendanceMetric] = field(default_factory=list)
    at_risk_students: list[AtRiskStudentMetric] = field(default_factory=list)

    @property
    def students_at_risk(self) -> int:
        return self.total_students_at_risk
