from dataclasses import dataclass
from uuid import UUID

from modules.report.domain.entities.student_report import StudentReport


@dataclass
class ClassReport:
    subject_class_id: UUID
    total_students: int
    class_average_frequency: float
    students_at_risk: int
    students: list[StudentReport]

    # Metadados de execução — usados para popular report_generation_logs
    strategy_used: str
    workers_used: int
    duration_ms: float
