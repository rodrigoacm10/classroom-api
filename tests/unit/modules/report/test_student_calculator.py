from uuid import uuid4

from modules.report.domain.entities.student_attendance_data import (
    RawConfirmation,
    StudentAttendanceData,
)
from modules.report.domain.services.student_calculator import (
    calculate_student_report,
    calculate_student_report_numpy,
    get_student_compute_fn,
)

ROOM_LAT, ROOM_LON = -8.0476, -34.8770


def test_calculators_puro_e_numpy_produzem_mesmo_relatorio():
    """Deve gerar o mesmo StudentReport com Haversine puro e com a versão vetorizada em NumPy."""
    data = StudentAttendanceData(
        tenant_member_id=uuid4(),
        student_name="Ana",
        total_sessions=10,
        confirmations=[
            RawConfirmation(ROOM_LAT, ROOM_LON, "regular"),
            RawConfirmation(ROOM_LAT + 0.0004, ROOM_LON, "regular"),
            RawConfirmation(ROOM_LAT + 0.01, ROOM_LON, "irregular"),
        ],
        room_lat=ROOM_LAT,
        room_lon=ROOM_LON,
        tolerance_radius_meters=50.0,
    )
    puro = calculate_student_report(data)
    numpy_result = calculate_student_report_numpy(data)

    assert puro.total_present == numpy_result.total_present == 2
    assert puro.total_absent == numpy_result.total_absent == 7
    assert puro.total_irregular == numpy_result.total_irregular == 1
    assert puro.frequency_rate == numpy_result.frequency_rate == 0.2
    assert puro.at_risk is True
    assert puro.avg_distance_meters == numpy_result.avg_distance_meters
    assert puro.confirmations_near_limit == numpy_result.confirmations_near_limit


def _data(**overrides) -> StudentAttendanceData:
    defaults = {
        "tenant_member_id": uuid4(),
        "student_name": "Ana",
        "total_sessions": 10,
        "confirmations": [],
        "room_lat": ROOM_LAT,
        "room_lon": ROOM_LON,
        "tolerance_radius_meters": 50.0,
    }
    return StudentAttendanceData(**{**defaults, **overrides})


def test_approved_conta_como_presenca():
    """Deve contar record_status=approved como presença válida, igual a regular."""
    report = calculate_student_report(
        _data(
            confirmations=[
                RawConfirmation(ROOM_LAT, ROOM_LON, "regular"),
                RawConfirmation(ROOM_LAT, ROOM_LON, "approved"),
            ]
        )
    )
    assert report.total_present == 2
    assert report.total_irregular == 0
    assert report.frequency_rate == 0.2


def test_rejected_nao_conta_como_presenca_nem_irregular():
    """Deve tratar rejected como confirmação (reduz falta) sem somar em presente nem irregular."""
    report = calculate_student_report(
        _data(confirmations=[RawConfirmation(ROOM_LAT, ROOM_LON, "rejected")])
    )
    assert report.total_present == 0
    assert report.total_irregular == 0
    assert report.total_absent == 9
    assert report.frequency_rate == 0.0
    assert report.at_risk is True


def test_zero_sessoes_retorna_frequencia_zero():
    """Deve devolver frequency_rate=0 e at_risk=True quando a turma ainda não tem sessões."""
    report = calculate_student_report(_data(total_sessions=0))
    assert report.frequency_rate == 0.0
    assert report.total_absent == 0
    assert report.at_risk is True
    assert report.avg_distance_meters == 0.0


def test_get_student_compute_fn_escolhe_versao_pela_strategy():
    """Deve devolver a fn NumPy só para thread_pool_numpy; as demais usam a versão pura."""
    assert get_student_compute_fn("thread_pool_numpy") is calculate_student_report_numpy
    assert get_student_compute_fn("process_pool") is calculate_student_report
    assert get_student_compute_fn("sequential") is calculate_student_report
