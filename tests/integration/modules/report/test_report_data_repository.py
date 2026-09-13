from datetime import datetime, timedelta, timezone

import pytest

from modules.attendance.domain.entities.attendance_session import AttendanceSession
from modules.attendance.infra.repositories.record_sqlalchemy_repository import (
    RecordSQLAlchemyRepository,
)
from modules.attendance.infra.repositories.session_sqlalchemy_repository import (
    SessionSQLAlchemyRepository,
)
from modules.enrollment.domain.entities.enrollment import Enrollment
from modules.enrollment.infra.repositories.enrollment_sqlalchemy_repository import (
    EnrollmentSQLAlchemyRepository,
)
from sqlalchemy import select

from infra.database.models.report_generation_log import ReportGenerationLogModel
from modules.report.infra.repositories.report_data_repository import ReportDataRepository
from modules.report.infra.repositories.report_generation_log_repository import (
    ReportGenerationLogRepository,
)
from modules.room.domain.entities.room import Room
from modules.room.infra.repositories.room_sqlalchemy_repository import RoomSQLAlchemyRepository
from modules.subject_class.domain.entities.subject_class import SubjectClass
from modules.subject_class.infra.repositories.subject_class_sqlalchemy_repository import (
    SubjectClassSQLAlchemyRepository,
)
from shared.enums.user_role import UserRole
from tests.factories.tenant_factory import TenantFactory
from tests.factories.user_factory import UserFactory


@pytest.mark.asyncio
class TestReportDataRepository:
    """
    Suíte de Testes (Integração): ReportDataRepository
    Valida a carga da turma no Postgres (confirmações, matrículas e sala).
    """


    async def _seed_class_with_students(self, session, n_students: int = 2):
        tenant = await TenantFactory.create(session)
        room_repo = RoomSQLAlchemyRepository(session)
        room = await room_repo.save(
            Room(
                tenant_id=tenant.id,
                name="Lab 1",
                latitude=-8.0476,
                longitude=-34.8770,
                tolerance_radius_meters=50,
            )
        )

        sc_repo = SubjectClassSQLAlchemyRepository(session)
        sc = await sc_repo.save(
            SubjectClass(
                tenant_id=tenant.id,
                name="Turma POO",
                discipline_name="Programação",
                room_id=room.id,
            )
        )

        enrollment_repo = EnrollmentSQLAlchemyRepository(session)
        members = []
        for i in range(n_students):
            user = await UserFactory.create(session, name=f"Aluno {i + 1}")
            member = await TenantFactory.create_member(
                session, tenant_id=tenant.id, user_id=user.id, role=UserRole.ALUNO
            )
            await enrollment_repo.save(
                Enrollment(subject_class_id=sc.id, tenant_member_id=member.id)
            )
            members.append(member)

        return tenant, room, sc, members

    async def test_load_class_data_agrupa_confirmacoes_por_aluno(self, session):
        """Deve agrupar em cada StudentAttendanceData exatamente as confirmações daquele aluno."""
        tenant, room, sc, members = await self._seed_class_with_students(session, n_students=2)
        student_a, student_b = members

        session_repo = SessionSQLAlchemyRepository(session)
        att_session = await session_repo.save(
            AttendanceSession(
                subject_class_id=sc.id,
                room_id=room.id,
                day_code="X3KP7Q",
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
            )
        )

        record_repo = RecordSQLAlchemyRepository(session)
        await record_repo.create_record(
            session_id=att_session.id,
            tenant_member_id=student_a.id,
            latitude=-8.04761,
            longitude=-34.87701,
            room_id=room.id,
            tolerance_radius_meters=50,
        )
        await record_repo.create_record(
            session_id=att_session.id,
            tenant_member_id=student_b.id,
            latitude=-8.04762,
            longitude=-34.87702,
            room_id=room.id,
            tolerance_radius_meters=50,
        )

        repo = ReportDataRepository(session)
        data = await repo.load_class_data(tenant.id, sc.id)

        assert len(data) == 2
        by_id = {item.tenant_member_id: item for item in data}
        assert len(by_id[student_a.id].confirmations) == 1
        assert len(by_id[student_b.id].confirmations) == 1
        assert by_id[student_a.id].total_sessions == 1
        assert by_id[student_b.id].total_sessions == 1
        assert by_id[student_a.id].student_name == "Aluno 1"
        assert abs(by_id[student_a.id].room_lat - (-8.0476)) < 0.0001
        assert by_id[student_a.id].tolerance_radius_meters == 50.0

    async def test_load_class_data_aluno_sem_confirmacoes_retorna_lista_vazia(self, session):
        """Deve devolver confirmations=[] para aluno matriculado que nunca confirmou presença."""
        tenant, room, sc, members = await self._seed_class_with_students(session, n_students=2)
        present_member, absent_member = members

        session_repo = SessionSQLAlchemyRepository(session)
        att_session = await session_repo.save(
            AttendanceSession(
                subject_class_id=sc.id,
                room_id=room.id,
                day_code="ABC123",
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
            )
        )

        record_repo = RecordSQLAlchemyRepository(session)
        await record_repo.create_record(
            session_id=att_session.id,
            tenant_member_id=present_member.id,
            latitude=-8.04761,
            longitude=-34.87701,
            room_id=room.id,
            tolerance_radius_meters=50,
        )

        repo = ReportDataRepository(session)
        data = await repo.load_class_data(tenant.id, sc.id)

        by_id = {item.tenant_member_id: item for item in data}
        assert len(by_id[present_member.id].confirmations) == 1
        assert by_id[absent_member.id].confirmations == []
        assert by_id[absent_member.id].total_sessions == 1

    async def test_load_class_data_ignora_matricula_deletada(self, session):
        """Deve omitir aluno cuja matrícula está com deleted=True."""
        tenant, _room, sc, members = await self._seed_class_with_students(session, n_students=2)
        active_member, deleted_member = members

        enrollment_repo = EnrollmentSQLAlchemyRepository(session)
        deleted_enrollment = await enrollment_repo.find_by_class_and_member(
            sc.id, deleted_member.id
        )
        assert deleted_enrollment is not None
        deleted_enrollment.deleted = True
        await enrollment_repo.save(deleted_enrollment)

        repo = ReportDataRepository(session)
        data = await repo.load_class_data(tenant.id, sc.id)

        ids = {item.tenant_member_id for item in data}
        assert active_member.id in ids
        assert deleted_member.id not in ids

    async def test_load_class_data_sem_sessoes_zera_total_e_confirmacoes(self, session):
        """Deve devolver total_sessions=0 e confirmations=[] quando a turma ainda não abriu chamada."""
        tenant, _room, sc, members = await self._seed_class_with_students(session, n_students=1)

        repo = ReportDataRepository(session)
        data = await repo.load_class_data(tenant.id, sc.id)

        assert len(data) == 1
        assert data[0].tenant_member_id == members[0].id
        assert data[0].total_sessions == 0
        assert data[0].confirmations == []

    async def test_load_class_data_turma_sem_sala_usa_defaults(self, session):
        """Deve usar lat/lon 0 e raio 50 quando a turma não tem room_id."""
        tenant = await TenantFactory.create(session)
        user = await UserFactory.create(session, name="Aluno Sem Sala")
        member = await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=user.id, role=UserRole.ALUNO
        )
        sc = await SubjectClassSQLAlchemyRepository(session).save(
            SubjectClass(
                tenant_id=tenant.id,
                name="Turma Online",
                discipline_name="POO",
                room_id=None,
            )
        )
        await EnrollmentSQLAlchemyRepository(session).save(
            Enrollment(subject_class_id=sc.id, tenant_member_id=member.id)
        )

        repo = ReportDataRepository(session)
        data = await repo.load_class_data(tenant.id, sc.id)

        assert len(data) == 1
        assert data[0].room_lat == 0.0
        assert data[0].room_lon == 0.0
        assert data[0].tolerance_radius_meters == 50.0


@pytest.mark.asyncio
class TestReportGenerationLogRepository:
    """
    Suíte de Testes (Integração): ReportGenerationLogRepository
    Valida a persistência da evidência de benchmark no Postgres.
    """

    async def test_create_persiste_log_de_execucao(self, session):
        """Deve gravar strategy, workers, itens e duration_ms em report_generation_logs."""
        tenant = await TenantFactory.create(session)
        sc = await SubjectClassSQLAlchemyRepository(session).save(
            SubjectClass(tenant_id=tenant.id, name="Turma Log", discipline_name="POO")
        )

        log_repo = ReportGenerationLogRepository(session)
        await log_repo.create(
            tenant_id=tenant.id,
            subject_class_id=sc.id,
            strategy="process_pool",
            workers_used=4,
            items_processed=40,
            duration_ms=123.45,
        )

        rows = (
            await session.execute(
                select(ReportGenerationLogModel).where(
                    ReportGenerationLogModel.subject_class_id == sc.id
                )
            )
        ).scalars().all()

        assert len(rows) == 1
        log = rows[0]
        assert log.tenant_id == tenant.id
        assert log.strategy == "process_pool"
        assert log.workers_used == 4
        assert log.items_processed == 40
        assert log.duration_ms == 123.45
        assert log.created_at is not None
