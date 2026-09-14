import numpy as np

from modules.report.domain.entities.student_attendance_data import StudentAttendanceData
from modules.report.domain.entities.student_report import StudentReport
from modules.report.domain.services.geo_metrics import (
    compute_student_geo_metrics,
    haversine_distance,
    haversine_distance_vectorized,
)

RISK_THRESHOLD = 0.75  # 75% de frequência mínima — configurável por tenant em etapa futura

_VALID_STATUSES = ("regular", "approved")
_IRREGULAR_STATUS = "irregular"


def _build_student_report(
    data: StudentAttendanceData, distances: list[float]
) -> StudentReport:
    valid = [c for c in data.confirmations if c.record_status in _VALID_STATUSES]
    irregular = [c for c in data.confirmations if c.record_status == _IRREGULAR_STATUS]

    present = len(valid)
    absent = data.total_sessions - len(data.confirmations)
    rate = present / data.total_sessions if data.total_sessions > 0 else 0.0

    geo = compute_student_geo_metrics(distances, data.tolerance_radius_meters)

    return StudentReport(
        tenant_member_id=data.tenant_member_id,
        student_name=data.student_name,
        total_present=present,
        total_absent=absent,
        total_irregular=len(irregular),
        frequency_rate=round(rate, 4),
        at_risk=rate < RISK_THRESHOLD,
        avg_distance_meters=geo["avg_distance_meters"],
        confirmations_near_limit=geo["confirmations_near_limit"],
    )


def calculate_student_report(data: StudentAttendanceData) -> StudentReport:
    """
    Função pura — roda IDENTICAMENTE em processo separado, thread separada
    ou chamada direta (sequencial). Não faz I/O de nenhuma espécie.

    Usa Haversine em Python puro — picklable, adequada para ProcessPoolStrategy.
    """
    distances = [
        haversine_distance(c.latitude, c.longitude, data.room_lat, data.room_lon)
        for c in data.confirmations
    ]
    return _build_student_report(data, distances)


def calculate_student_report_numpy(data: StudentAttendanceData) -> StudentReport:
    """
    Mesma regra de `calculate_student_report`, com Haversine vetorizado em NumPy.

    As operações trigonométricas do NumPy liberam o GIL, o que torna esta função
    a única adequada para ThreadPoolNumpyStrategy.
    """
    if not data.confirmations:
        distances: list[float] = []
    else:
        lats = np.array([c.latitude for c in data.confirmations], dtype=float)
        lons = np.array([c.longitude for c in data.confirmations], dtype=float)
        distances = haversine_distance_vectorized(
            lats, lons, data.room_lat, data.room_lon
        ).tolist()
    return _build_student_report(data, distances)


def get_student_compute_fn(strategy_name: str):
    """Seleciona a função-alvo compatível com a estratégia de paralelismo."""
    if strategy_name == "thread_pool_numpy":
        return calculate_student_report_numpy
    return calculate_student_report
