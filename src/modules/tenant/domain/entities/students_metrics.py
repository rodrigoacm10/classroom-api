from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class StudentsMetrics:
    """Indicadores consolidados dos alunos da instituição ou do escopo do professor."""

    total_students: int
    avg_classes_per_student: float
    total_enrollments: int
    average_attendance_rate: float
    students_at_risk: int
    students_no_class: int
