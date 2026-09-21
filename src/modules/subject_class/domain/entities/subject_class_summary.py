from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass
class SubjectClassSummary:
    """Read-model da listagem de turmas, com agregados de matrícula e frequência."""

    id: UUID
    tenant_id: UUID
    professor_id: UUID | None
    professor_name: str | None
    room_id: UUID | None
    name: str
    discipline_name: str
    student_count: int
    attendance_rate: float
    created_at: datetime
    updated_at: datetime

    @staticmethod
    def compute_attendance_rate(
        present_count: int, student_count: int, session_count: int
    ) -> float:
        """Média da turma: presentes válidos / (alunos ativos × sessões não canceladas)."""
        if student_count <= 0 or session_count <= 0:
            return 0.0
        return round(present_count / (student_count * session_count), 4)
