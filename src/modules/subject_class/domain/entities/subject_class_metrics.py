from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SubjectClassMetrics:
    total_classes: int
    active_classes: int
    inactive_classes: int
    total_students: int
    average_attendance_rate: float
    at_risk_classes_count: int
    live_classes_count: int
