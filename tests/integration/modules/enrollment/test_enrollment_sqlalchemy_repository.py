from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from modules.attendance.domain.entities.attendance_record import AttendanceRecord
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
from modules.room.domain.entities.room import Room
from modules.room.infra.repositories.room_sqlalchemy_repository import RoomSQLAlchemyRepository
from modules.subject_class.domain.entities.subject_class import SubjectClass
from modules.subject_class.infra.repositories.subject_class_sqlalchemy_repository import (
    SubjectClassSQLAlchemyRepository,
)
from shared.enums.drop_reason import DropReason
from shared.enums.enrollment_status import EnrollmentStatus
from shared.enums.record_status import RecordStatus
from shared.enums.session_status import SessionStatus
from shared.enums.user_role import UserRole
from tests.factories.tenant_factory import TenantFactory
from tests.factories.user_factory import UserFactory


@pytest.mark.asyncio
class TestEnrollmentSQLAlchemyRepository:

    async def test_save_and_find_by_id(self, session):
        """Deve persistir uma matrícula no banco de dados e recuperá-la por ID."""
        user = await UserFactory.create(session)
        tenant = await TenantFactory.create(session)
        member = await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=user.id, role=UserRole.ALUNO
        )

        sc_repo = SubjectClassSQLAlchemyRepository(session)
        sc = await sc_repo.save(
            SubjectClass(tenant_id=tenant.id, name="Turma A", discipline_name="Math")
        )

        repo = EnrollmentSQLAlchemyRepository(session)
        enrollment = Enrollment(subject_class_id=sc.id, tenant_member_id=member.id)

        saved = await repo.save(enrollment)
        assert saved.id is not None
        assert saved.subject_class_id == sc.id
        assert saved.tenant_member_id == member.id
        assert saved.status == EnrollmentStatus.ACTIVE
        assert saved.deleted is False

        found = await repo.find_by_id(saved.id)
        assert found is not None
        assert found.id == saved.id

    async def test_find_by_class_and_member(self, session):
        """Deve encontrar a matrícula ativa por turma e membro."""
        user = await UserFactory.create(session)
        tenant = await TenantFactory.create(session)
        member = await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=user.id, role=UserRole.ALUNO
        )

        sc_repo = SubjectClassSQLAlchemyRepository(session)
        sc = await sc_repo.save(
            SubjectClass(tenant_id=tenant.id, name="Turma B", discipline_name="Physics")
        )

        repo = EnrollmentSQLAlchemyRepository(session)
        saved = await repo.save(Enrollment(subject_class_id=sc.id, tenant_member_id=member.id))

        found = await repo.find_by_class_and_member(sc.id, member.id)
        assert found is not None
        assert found.id == saved.id

    async def test_list_by_subject_class_with_status_and_deleted_filters(self, session):
        """Deve listar matrículas por turma filtrando por status e deleted."""
        user1 = await UserFactory.create(session)
        user2 = await UserFactory.create(session)
        user3 = await UserFactory.create(session)

        tenant = await TenantFactory.create(session)
        m1 = await TenantFactory.create_member(session, tenant_id=tenant.id, user_id=user1.id, role=UserRole.ALUNO)
        m2 = await TenantFactory.create_member(session, tenant_id=tenant.id, user_id=user2.id, role=UserRole.ALUNO)
        m3 = await TenantFactory.create_member(session, tenant_id=tenant.id, user_id=user3.id, role=UserRole.ALUNO)

        sc_repo = SubjectClassSQLAlchemyRepository(session)
        sc = await sc_repo.save(SubjectClass(tenant_id=tenant.id, name="Turma C", discipline_name="History"))

        repo = EnrollmentSQLAlchemyRepository(session)
        e1 = await repo.save(Enrollment(subject_class_id=sc.id, tenant_member_id=m1.id, status=EnrollmentStatus.ACTIVE))
        e2 = await repo.save(Enrollment(subject_class_id=sc.id, tenant_member_id=m2.id, status=EnrollmentStatus.DROPPED))
        e3 = await repo.save(Enrollment(subject_class_id=sc.id, tenant_member_id=m3.id, status=EnrollmentStatus.ACTIVE, deleted=True))

        active_list = await repo.list_by_subject_class(sc.id, status=EnrollmentStatus.ACTIVE)
        assert len(active_list) == 1
        assert active_list[0].id == e1.id

        non_deleted_list = await repo.list_by_subject_class(sc.id)
        assert len(non_deleted_list) == 2

        all_list = await repo.list_by_subject_class(sc.id, include_deleted=True)
        assert len(all_list) == 3

    async def test_drop_all_active_for_member(self, session):
        """Deve alterar em lote o status de todas as matrículas ativas de um membro para DROPPED."""
        user = await UserFactory.create(session)
        tenant = await TenantFactory.create(session)
        member = await TenantFactory.create_member(session, tenant_id=tenant.id, user_id=user.id, role=UserRole.ALUNO)

        sc_repo = SubjectClassSQLAlchemyRepository(session)
        sc1 = await sc_repo.save(SubjectClass(tenant_id=tenant.id, name="T1", discipline_name="D1"))
        sc2 = await sc_repo.save(SubjectClass(tenant_id=tenant.id, name="T2", discipline_name="D2"))

        repo = EnrollmentSQLAlchemyRepository(session)
        e1 = await repo.save(Enrollment(subject_class_id=sc1.id, tenant_member_id=member.id, status=EnrollmentStatus.ACTIVE))
        e2 = await repo.save(Enrollment(subject_class_id=sc2.id, tenant_member_id=member.id, status=EnrollmentStatus.ACTIVE))

        affected_count = await repo.drop_all_active_for_member(member.id)
        assert affected_count == 2

        res_e1 = await repo.find_by_id(e1.id)
        res_e2 = await repo.find_by_id(e2.id)
        assert res_e1 is not None
        assert res_e2 is not None
        assert res_e1.status == EnrollmentStatus.DROPPED
        assert res_e2.status == EnrollmentStatus.DROPPED
        assert res_e1.dropped_at is not None
        assert res_e1.drop_reason is not None
        assert res_e1.drop_reason == DropReason.ROLE_CHANGE

    async def test_list_by_member(self, session):
        """Deve listar todas as matrículas de um aluno específico."""
        user = await UserFactory.create(session)
        tenant = await TenantFactory.create(session)
        member = await TenantFactory.create_member(session, tenant_id=tenant.id, user_id=user.id, role=UserRole.ALUNO)

        sc_repo = SubjectClassSQLAlchemyRepository(session)
        sc1 = await sc_repo.save(SubjectClass(tenant_id=tenant.id, name="T1", discipline_name="D1"))
        sc2 = await sc_repo.save(SubjectClass(tenant_id=tenant.id, name="T2", discipline_name="D2"))

        repo = EnrollmentSQLAlchemyRepository(session)
        await repo.save(Enrollment(subject_class_id=sc1.id, tenant_member_id=member.id, status=EnrollmentStatus.ACTIVE))
        await repo.save(Enrollment(subject_class_id=sc2.id, tenant_member_id=member.id, status=EnrollmentStatus.DROPPED))

        member_list = await repo.list_by_member(member.id)
        assert len(member_list) == 2

    async def test_partial_unique_index_allows_new_enrollment_after_soft_delete(self, session):
        """O partial unique index 'uq_enrollment_active' deve impedir duplicidade de ativos, mas permitir nova matrícula se a anterior tiver deleted=True."""
        user = await UserFactory.create(session)
        tenant = await TenantFactory.create(session)
        member = await TenantFactory.create_member(session, tenant_id=tenant.id, user_id=user.id, role=UserRole.ALUNO)

        sc_repo = SubjectClassSQLAlchemyRepository(session)
        sc = await sc_repo.save(SubjectClass(tenant_id=tenant.id, name="Turma Index", discipline_name="Test"))

        repo = EnrollmentSQLAlchemyRepository(session)
        # 1. Primeira matrícula ativa
        e1 = await repo.save(Enrollment(subject_class_id=sc.id, tenant_member_id=member.id))

        # 2. Tentar inserir segunda matrícula idêntica em savepoint deve falhar pelo partial index
        async with session.begin_nested():
            e2_duplicate = Enrollment(subject_class_id=sc.id, tenant_member_id=member.id)
            with pytest.raises(IntegrityError):
                await repo.save(e2_duplicate)

        # 3. Soft-delete da primeira matrícula
        e1.deleted = True
        await repo.save(e1)

        # 4. Nova matrícula idêntica agora DEVE funcionar devido ao postgresql_where deleted = false
        e3_new = Enrollment(subject_class_id=sc.id, tenant_member_id=member.id)
        saved_e3 = await repo.save(e3_new)
        assert saved_e3.id is not None
        assert saved_e3.id != e1.id

    async def test_find_active_fcm_tokens_returns_all_student_device_tokens(self, session):
        """Deve retornar os tokens FCM de todos os dispositivos (celular + tablet) dos alunos ativos da turma."""
        from modules.notification.domain.entities.fcm_token import FCMToken
        from modules.notification.infra.repositories.fcm_token_sqlalchemy_repository import (
            FCMTokenSQLAlchemyRepository,
        )

        user1 = await UserFactory.create(session)  # Aluno 1 (com celular e tablet)
        user2 = await UserFactory.create(session)  # Aluno 2 (com apenas celular)
        tenant = await TenantFactory.create(session)

        m1 = await TenantFactory.create_member(session, tenant_id=tenant.id, user_id=user1.id, role=UserRole.ALUNO)
        m2 = await TenantFactory.create_member(session, tenant_id=tenant.id, user_id=user2.id, role=UserRole.ALUNO)

        sc_repo = SubjectClassSQLAlchemyRepository(session)
        sc = await sc_repo.save(SubjectClass(tenant_id=tenant.id, name="Turma FCM", discipline_name="Mobile"))

        repo = EnrollmentSQLAlchemyRepository(session)
        await repo.save(Enrollment(subject_class_id=sc.id, tenant_member_id=m1.id, status=EnrollmentStatus.ACTIVE))
        await repo.save(Enrollment(subject_class_id=sc.id, tenant_member_id=m2.id, status=EnrollmentStatus.ACTIVE))

        # Cadastra tokens de celular e tablet no banco
        fcm_repo = FCMTokenSQLAlchemyRepository(session)
        await fcm_repo.upsert(FCMToken(user_id=user1.id, device_id="dev-mobile-1", fcm_token="token-user1-mobile", platform="android"))
        await fcm_repo.upsert(FCMToken(user_id=user1.id, device_id="dev-tablet-1", fcm_token="token-user1-tablet", platform="ios"))
        await fcm_repo.upsert(FCMToken(user_id=user2.id, device_id="dev-mobile-2", fcm_token="token-user2-mobile", platform="android"))

        tokens = await repo.find_active_fcm_tokens(sc.id)
        assert len(tokens) == 3
        assert "token-user1-mobile" in tokens
        assert "token-user1-tablet" in tokens
        assert "token-user2-mobile" in tokens

    async def test_list_summaries_by_member_includes_class_room_professor_and_rate(self, session):
        """Listagem do aluno agrega turma, sala, professor e taxa de presença individual."""

        tenant = await TenantFactory.create(session)
        professor = await UserFactory.create(session, name="Prof Ana")
        prof_member = await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=professor.id, role=UserRole.PROFESSOR
        )
        student = await UserFactory.create(session, name="Aluno João")
        student_member = await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=student.id, role=UserRole.ALUNO
        )
        other_student = await UserFactory.create(session, name="Outro Aluno")
        other_member = await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=other_student.id, role=UserRole.ALUNO
        )

        room = await RoomSQLAlchemyRepository(session).save(
            Room(tenant_id=tenant.id, name="Lab 101", latitude=-8.0, longitude=-34.0)
        )
        sc_repo = SubjectClassSQLAlchemyRepository(session)
        attended = await sc_repo.save(
            SubjectClass(
                tenant_id=tenant.id,
                professor_id=prof_member.id,
                room_id=room.id,
                name="POO",
                discipline_name="Programação",
            )
        )
        empty = await sc_repo.save(
            SubjectClass(
                tenant_id=tenant.id,
                professor_id=prof_member.id,
                room_id=room.id,
                name="Cálculo",
                discipline_name="Matemática",
            )
        )

        repo = EnrollmentSQLAlchemyRepository(session)
        await repo.save(Enrollment(subject_class_id=attended.id, tenant_member_id=student_member.id))
        await repo.save(Enrollment(subject_class_id=empty.id, tenant_member_id=student_member.id))
        await repo.save(Enrollment(subject_class_id=attended.id, tenant_member_id=other_member.id))

        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
        session_repo = SessionSQLAlchemyRepository(session)
        closed = await session_repo.save(
            AttendanceSession(
                subject_class_id=attended.id,
                room_id=room.id,
                day_code="AAA111",
                expires_at=expires_at,
                status=SessionStatus.CLOSED,
                closed_at=datetime.now(timezone.utc),
            )
        )
        await session_repo.save(
            AttendanceSession(
                subject_class_id=attended.id,
                room_id=room.id,
                day_code="BBB222",
                expires_at=expires_at,
                status=SessionStatus.CLOSED,
                closed_at=datetime.now(timezone.utc),
            )
        )
        await session_repo.save(
            AttendanceSession(
                subject_class_id=attended.id,
                room_id=room.id,
                day_code="CCC333",
                expires_at=expires_at,
                status=SessionStatus.CANCELLED,
                closed_at=datetime.now(timezone.utc),
            )
        )

        record_repo = RecordSQLAlchemyRepository(session)
        await record_repo.save(
            AttendanceRecord(
                session_id=closed.id,
                tenant_member_id=student_member.id,
                latitude=-8.0,
                longitude=-34.0,
                distance_meters=1.0,
                within_radius=True,
                record_status=RecordStatus.REGULAR,
            )
        )
        await record_repo.save(
            AttendanceRecord(
                session_id=closed.id,
                tenant_member_id=other_member.id,
                latitude=-8.0,
                longitude=-34.0,
                distance_meters=1.0,
                within_radius=True,
                record_status=RecordStatus.REGULAR,
            )
        )

        summaries = await repo.list_summaries_by_member(tenant.id, student_member.id)
        by_class = {item.subject_class_id: item for item in summaries}
        assert len(summaries) == 2

        calc = by_class[empty.id]
        assert calc.name == "Cálculo"
        assert calc.room_name == "Lab 101"
        assert calc.professor_name == "Prof Ana"
        assert calc.attendance_rate == 0.0

    async def test_find_by_class_paginated_with_status_and_deleted_filters(self, session) -> None:
        """Deve paginar matrículas por offset e aplicar filtros de status e include_deleted."""
        from shared.pagination import PaginationParams

        tenant = await TenantFactory.create(session)
        user1 = await UserFactory.create(session)
        user2 = await UserFactory.create(session)
        m1 = await TenantFactory.create_member(session, tenant_id=tenant.id, user_id=user1.id, role=UserRole.ALUNO)
        m2 = await TenantFactory.create_member(session, tenant_id=tenant.id, user_id=user2.id, role=UserRole.ALUNO)

        sc_repo = SubjectClassSQLAlchemyRepository(session)
        sc = await sc_repo.save(SubjectClass(tenant_id=tenant.id, name="Biologia", discipline_name="Ciências"))

        repo = EnrollmentSQLAlchemyRepository(session)
        e1 = Enrollment(subject_class_id=sc.id, tenant_member_id=m1.id, status=EnrollmentStatus.ACTIVE)
        e2 = Enrollment(subject_class_id=sc.id, tenant_member_id=m2.id, status=EnrollmentStatus.DROPPED)
        await repo.save(e1)
        await repo.save(e2)

        page_all = await repo.find_by_class_paginated(
            subject_class_id=sc.id,
            pagination=PaginationParams(page=1, page_size=1),
        )
        assert page_all.total == 2
        assert len(page_all.items) == 1
        assert page_all.pages == 2

        page_active = await repo.find_by_class_paginated(
            subject_class_id=sc.id,
            pagination=PaginationParams(page=1, page_size=10),
            status=EnrollmentStatus.ACTIVE,
        )
        assert page_active.total == 1
        assert page_active.items[0].tenant_member_id == m1.id
