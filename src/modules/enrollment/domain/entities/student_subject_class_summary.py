from dataclasses import dataclass
from uuid import UUID

from shared.enums.enrollment_status import EnrollmentStatus


@dataclass
class StudentSubjectClassSummary:
    """Read-model das turmas do aluno, com local, professor e taxa de presença individual."""

    enrollment_id: UUID
    subject_class_id: UUID
    name: str
    discipline_name: str
    room_id: UUID | None
    room_name: str | None
    professor_id: UUID | None
    professor_name: str | None
    attendance_rate: float
    status: EnrollmentStatus

    @staticmethod
    def compute_attendance_rate(present_count: int, session_count: int) -> float:
        """Taxa do aluno: presentes válidos / sessões não canceladas da turma."""
        if session_count <= 0:
            return 0.0
        return round(present_count / session_count, 4)
