from uuid import uuid4

import pytest

from modules.enrollment.domain.entities.student_metrics import StudentMetrics
from modules.enrollment.domain.entities.student_subject_class_summary import (
    StudentSubjectClassSummary,
)
from shared.enums.enrollment_status import EnrollmentStatus


class TestStudentSubjectClassSummaryEntity:
    def test_compute_attendance_rate_normal(self):
        """Calcula taxa de presença com 4 casas decimais."""
        # 3 de 4 -> 0.75
        assert StudentSubjectClassSummary.compute_attendance_rate(3, 4) == 0.75
        # 1 de 3 -> 0.3333
        assert StudentSubjectClassSummary.compute_attendance_rate(1, 3) == 0.3333
        # 0 de 5 -> 0.0
        assert StudentSubjectClassSummary.compute_attendance_rate(0, 5) == 0.0
        # 5 de 5 -> 1.0
        assert StudentSubjectClassSummary.compute_attendance_rate(5, 5) == 1.0

    def test_compute_attendance_rate_zero_or_negative_sessions(self):
        """Retorna 0.0 quando a quantidade de sessões for zero ou negativa."""
        assert StudentSubjectClassSummary.compute_attendance_rate(0, 0) == 0.0
        assert StudentSubjectClassSummary.compute_attendance_rate(2, 0) == 0.0
        assert StudentSubjectClassSummary.compute_attendance_rate(0, -1) == 0.0

    def test_summary_defaults(self):
        """Valida valores padrão para total_sessions e absences_count."""
        summary = StudentSubjectClassSummary(
            enrollment_id=uuid4(),
            subject_class_id=uuid4(),
            name="Redes de Computadores",
            discipline_name="RC-01",
            room_id=None,
            room_name=None,
            professor_id=None,
            professor_name=None,
            attendance_rate=0.0,
            status=EnrollmentStatus.ACTIVE,
        )
        assert summary.total_sessions == 0
        assert summary.absences_count == 0


class TestStudentMetricsEntity:
    def test_student_metrics_frozen(self):
        """Garante que a entidade StudentMetrics é imutável."""
        metrics = StudentMetrics(
            total_classes=4,
            average_attendance_rate=0.85,
            at_risk_count=1,
        )
        assert metrics.total_classes == 4
        assert metrics.average_attendance_rate == 0.85
        assert metrics.at_risk_count == 1

        with pytest.raises(AttributeError):
            metrics.total_classes = 5  # type: ignore[misc]
