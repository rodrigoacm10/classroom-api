from uuid import uuid4

import pytest

from modules.report.application.use_cases.generate_class_report import (
    GenerateClassReportInput,
    GenerateClassReportUseCase,
)
from modules.report.application.use_cases.get_student_report import (
    GetStudentReportInput,
    GetStudentReportUseCase,
)
from modules.report.domain.entities.student_attendance_data import (
    RawConfirmation,
    StudentAttendanceData,
)
from modules.subject_class.domain.entities.subject_class import SubjectClass
from shared.exceptions import ResourceNotFoundException
from shared.parallel.process_pool_strategy import ProcessPoolStrategy
from shared.parallel.sequential_strategy import SequentialStrategy
from shared.parallel.thread_pool_numpy_strategy import ThreadPoolNumpyStrategy
from tests.factories.tenant_factory import TenantFactory
from tests.unit.fakes.fake_report_repository import (
    FakeReportDataRepository,
    FakeReportGenerationLogRepository,
)
from tests.unit.fakes.fake_subject_class_repository import FakeSubjectClassRepository
from tests.unit.fakes.fake_tenant_repository import FakeTenantRepository

ROOM_LAT, ROOM_LON = -8.0476, -34.8770


def _make_student(
    *,
    name: str,
    total_sessions: int,
    n_regular: int,
    n_irregular: int = 0,
    tenant_member_id=None,
) -> StudentAttendanceData:
    confirmations = [
        RawConfirmation(latitude=ROOM_LAT, longitude=ROOM_LON, record_status="regular")
        for _ in range(n_regular)
    ] + [
        RawConfirmation(
            latitude=ROOM_LAT + 0.01,
            longitude=ROOM_LON,
            record_status="irregular",
        )
        for _ in range(n_irregular)
    ]
    return StudentAttendanceData(
        tenant_member_id=tenant_member_id or uuid4(),
        student_name=name,
        total_sessions=total_sessions,
        confirmations=confirmations,
        room_lat=ROOM_LAT,
        room_lon=ROOM_LON,
        tolerance_radius_meters=50.0,
    )


async def _setup(strategy=None):
    tenant_repo = FakeTenantRepository()
    subject_class_repo = FakeSubjectClassRepository()
    report_data_repo = FakeReportDataRepository()
    log_repo = FakeReportGenerationLogRepository()

    tenant = TenantFactory.make()
    await tenant_repo.save(tenant)

    subject_class = SubjectClass(
        tenant_id=tenant.id,
        name="Turma POO",
        discipline_name="POO",
    )
    await subject_class_repo.save(subject_class)

    use_case = GenerateClassReportUseCase(
        report_data_repo=report_data_repo,
        subject_class_repo=subject_class_repo,
        tenant_repo=tenant_repo,
        compute_strategy=strategy or SequentialStrategy(),
        log_repo=log_repo,
    )
    return tenant, subject_class, report_data_repo, log_repo, use_case


@pytest.mark.asyncio
class TestGenerateClassReportUseCase:
    """
    Suíte de Testes: GenerateClassReportUseCase
    Valida agregação da turma, risco, log de execução e equivalência entre strategies.
    """

    async def test_relatorio_calcula_frequencia_correta(self):
        """Deve calcular frequency_rate = 0.8 para aluno presente em 8 de 10 sessões."""
        tenant, subject_class, report_data_repo, _, use_case = await _setup()
        report_data_repo.data = [
            _make_student(name="Ana", total_sessions=10, n_regular=8),
        ]

        report = await use_case.execute(
            GenerateClassReportInput(tenant_id=tenant.id, subject_class_id=subject_class.id)
        )

        assert report.total_students == 1
        student = report.students[0]
        assert student.total_present == 8
        assert student.total_absent == 2
        assert student.frequency_rate == 0.8
        assert student.at_risk is False
        assert report.class_average_frequency == 0.8

    async def test_relatorio_marca_at_risk_abaixo_do_limite(self):
        """Deve marcar at_risk=True quando a frequência do aluno fica abaixo de 75%."""
        tenant, subject_class, report_data_repo, _, use_case = await _setup()
        report_data_repo.data = [
            _make_student(name="Bruno", total_sessions=10, n_regular=7),
        ]

        report = await use_case.execute(
            GenerateClassReportInput(tenant_id=tenant.id, subject_class_id=subject_class.id)
        )

        student = report.students[0]
        assert student.frequency_rate == 0.7
        assert student.at_risk is True
        assert report.students_at_risk == 1

    async def test_relatorio_registra_log_de_execucao(self):
        """Deve gravar um log de execução com strategy, workers_used e duration_ms após gerar o relatório."""
        tenant, subject_class, report_data_repo, log_repo, use_case = await _setup()
        report_data_repo.data = [
            _make_student(name="Ana", total_sessions=4, n_regular=4),
        ]

        report = await use_case.execute(
            GenerateClassReportInput(tenant_id=tenant.id, subject_class_id=subject_class.id)
        )

        assert len(log_repo.logs) == 1
        log = log_repo.logs[0]
        assert log["strategy"] == "sequential"
        assert log["workers_used"] == 1
        assert log["items_processed"] == 1
        assert log["duration_ms"] >= 0
        assert report.strategy_used == "sequential"
        assert report.workers_used == 1

    async def test_relatorio_falha_404_se_turma_nao_encontrada(self):
        """Deve lançar ResourceNotFoundException quando a turma não existe ou foi deletada."""
        tenant, _, _, _, use_case = await _setup()

        with pytest.raises(ResourceNotFoundException, match="Turma não encontrada"):
            await use_case.execute(
                GenerateClassReportInput(tenant_id=tenant.id, subject_class_id=uuid4())
            )

    async def test_relatorio_falha_404_se_tenant_nao_encontrado(self):
        """Deve lançar ResourceNotFoundException quando a instituição/tenant não existe."""
        _, subject_class, _, _, use_case = await _setup()

        with pytest.raises(ResourceNotFoundException, match="Instituição/tenant não encontrada"):
            await use_case.execute(
                GenerateClassReportInput(tenant_id=uuid4(), subject_class_id=subject_class.id)
            )

    async def test_resultado_e_identico_entre_estrategias(self):
        """Deve produzir StudentReports idênticos com Sequential, ProcessPool e ThreadPoolNumpy."""
        students = [
            _make_student(name="Ana", total_sessions=10, n_regular=8, n_irregular=1),
            _make_student(name="Bruno", total_sessions=10, n_regular=5),
            _make_student(name="Carla", total_sessions=10, n_regular=10),
        ]

        reports = []
        for strategy in (
            SequentialStrategy(),
            ProcessPoolStrategy(max_workers=2),
            ThreadPoolNumpyStrategy(max_workers=2),
        ):
            tenant, subject_class, report_data_repo, _, use_case = await _setup(strategy)
            report_data_repo.data = students
            report = await use_case.execute(
                GenerateClassReportInput(tenant_id=tenant.id, subject_class_id=subject_class.id)
            )
            reports.append(report)

        seq, process, thread = reports
        assert seq.total_students == process.total_students == thread.total_students
        assert seq.class_average_frequency == process.class_average_frequency == thread.class_average_frequency
        assert seq.students_at_risk == process.students_at_risk == thread.students_at_risk

        for a, b, c in zip(seq.students, process.students, thread.students, strict=True):
            assert a.tenant_member_id == b.tenant_member_id == c.tenant_member_id
            assert a.frequency_rate == b.frequency_rate == c.frequency_rate
            assert a.total_present == b.total_present == c.total_present
            assert a.total_absent == b.total_absent == c.total_absent
            assert a.total_irregular == b.total_irregular == c.total_irregular
            assert a.at_risk == b.at_risk == c.at_risk
            assert a.avg_distance_meters == b.avg_distance_meters == c.avg_distance_meters
            assert a.confirmations_near_limit == b.confirmations_near_limit == c.confirmations_near_limit

        assert seq.strategy_used == "sequential"
        assert process.strategy_used == "process_pool"
        assert thread.strategy_used == "thread_pool_numpy"

    async def test_ordena_alunos_pela_menor_frequencia(self):
        """Deve ordenar a lista da turma por frequency_rate crescente (maior risco primeiro)."""
        tenant, subject_class, report_data_repo, _, use_case = await _setup()
        report_data_repo.data = [
            _make_student(name="Carla", total_sessions=10, n_regular=10),
            _make_student(name="Bruno", total_sessions=10, n_regular=5),
            _make_student(name="Ana", total_sessions=10, n_regular=8),
        ]

        report = await use_case.execute(
            GenerateClassReportInput(tenant_id=tenant.id, subject_class_id=subject_class.id)
        )

        assert [s.student_name for s in report.students] == ["Bruno", "Ana", "Carla"]
        assert report.class_average_frequency == 0.7667
        assert report.students_at_risk == 1

    async def test_turma_sem_alunos_retorna_agregados_zerados(self):
        """Deve devolver totais zerados e lista vazia quando a turma não tem matriculados."""
        tenant, subject_class, _, log_repo, use_case = await _setup()

        report = await use_case.execute(
            GenerateClassReportInput(tenant_id=tenant.id, subject_class_id=subject_class.id)
        )

        assert report.total_students == 0
        assert report.class_average_frequency == 0.0
        assert report.students_at_risk == 0
        assert report.students == []
        assert log_repo.logs[0]["items_processed"] == 0


@pytest.mark.asyncio
class TestGetStudentReportUseCase:
    """
    Suíte de Testes: GetStudentReportUseCase
    Valida o detalhe de frequência de um aluno matriculado na turma.
    """

    async def test_retorna_relatorio_do_aluno(self):
        """Deve retornar o StudentReport do aluno pedido, sem misturar com os colegas."""
        tenant_repo = FakeTenantRepository()
        subject_class_repo = FakeSubjectClassRepository()
        report_data_repo = FakeReportDataRepository()

        tenant = TenantFactory.make()
        await tenant_repo.save(tenant)
        subject_class = SubjectClass(
            tenant_id=tenant.id, name="Turma POO", discipline_name="POO"
        )
        await subject_class_repo.save(subject_class)

        member_id = uuid4()
        report_data_repo.data = [
            _make_student(name="Ana", total_sessions=10, n_regular=8, tenant_member_id=member_id),
            _make_student(name="Bruno", total_sessions=10, n_regular=3),
        ]

        use_case = GetStudentReportUseCase(
            report_data_repo=report_data_repo,
            subject_class_repo=subject_class_repo,
            tenant_repo=tenant_repo,
        )
        report = await use_case.execute(
            GetStudentReportInput(
                tenant_id=tenant.id,
                subject_class_id=subject_class.id,
                tenant_member_id=member_id,
            )
        )
        assert report.student_name == "Ana"
        assert report.frequency_rate == 0.8
        assert report.tenant_member_id == member_id

    async def test_aluno_inexistente_retorna_404(self):
        """Deve lançar ResourceNotFoundException quando o aluno não está matriculado na turma."""
        tenant_repo = FakeTenantRepository()
        subject_class_repo = FakeSubjectClassRepository()
        report_data_repo = FakeReportDataRepository()

        tenant = TenantFactory.make()
        await tenant_repo.save(tenant)
        subject_class = SubjectClass(
            tenant_id=tenant.id, name="Turma POO", discipline_name="POO"
        )
        await subject_class_repo.save(subject_class)

        use_case = GetStudentReportUseCase(
            report_data_repo=report_data_repo,
            subject_class_repo=subject_class_repo,
            tenant_repo=tenant_repo,
        )
        with pytest.raises(ResourceNotFoundException, match="Aluno não encontrado"):
            await use_case.execute(
                GetStudentReportInput(
                    tenant_id=tenant.id,
                    subject_class_id=subject_class.id,
                    tenant_member_id=uuid4(),
                )
            )

    async def test_falha_404_se_tenant_nao_encontrado(self):
        """Deve lançar ResourceNotFoundException quando a instituição/tenant não existe."""
        subject_class_repo = FakeSubjectClassRepository()
        use_case = GetStudentReportUseCase(
            report_data_repo=FakeReportDataRepository(),
            subject_class_repo=subject_class_repo,
            tenant_repo=FakeTenantRepository(),
        )
        with pytest.raises(ResourceNotFoundException, match="Instituição/tenant não encontrada"):
            await use_case.execute(
                GetStudentReportInput(
                    tenant_id=uuid4(),
                    subject_class_id=uuid4(),
                    tenant_member_id=uuid4(),
                )
            )

    async def test_falha_404_se_turma_nao_encontrada(self):
        """Deve lançar ResourceNotFoundException quando a turma não existe."""
        tenant_repo = FakeTenantRepository()
        tenant = TenantFactory.make()
        await tenant_repo.save(tenant)
        use_case = GetStudentReportUseCase(
            report_data_repo=FakeReportDataRepository(),
            subject_class_repo=FakeSubjectClassRepository(),
            tenant_repo=tenant_repo,
        )
        with pytest.raises(ResourceNotFoundException, match="Turma não encontrada"):
            await use_case.execute(
                GetStudentReportInput(
                    tenant_id=tenant.id,
                    subject_class_id=uuid4(),
                    tenant_member_id=uuid4(),
                )
            )
