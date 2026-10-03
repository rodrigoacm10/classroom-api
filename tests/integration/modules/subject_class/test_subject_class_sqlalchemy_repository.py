from datetime import datetime, timedelta, timezone

import pytest

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
from shared.enums.enrollment_status import EnrollmentStatus
from shared.enums.record_status import RecordStatus
from shared.enums.session_status import SessionStatus
from shared.enums.user_role import UserRole
from shared.pagination import PaginationParams
from tests.factories.tenant_factory import TenantFactory
from tests.factories.user_factory import UserFactory


@pytest.mark.asyncio
class TestSubjectClassSQLAlchemyRepository:
    async def test_save_and_find_by_id(self, session):
        """Deve persistir uma turma no banco de dados e recuperá-la por ID com sucesso."""
        user = await UserFactory.create(session)
        tenant = await TenantFactory.create(session)
        member = await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=user.id, role=UserRole.PROFESSOR
        )

        room_repo = RoomSQLAlchemyRepository(session)
        room = await room_repo.save(
            Room(tenant_id=tenant.id, name="Sala 101", latitude=-8.0, longitude=-34.0)
        )

        repo = SubjectClassSQLAlchemyRepository(session)
        sc = SubjectClass(
            tenant_id=tenant.id,
            professor_id=member.id,
            room_id=room.id,
            name="Turma BD",
            discipline_name="Banco de Dados",
        )

        saved = await repo.save(sc)
        assert saved.id is not None

        found = await repo.find_by_id(saved.id)
        assert found is not None
        assert found.name == "Turma BD"
        assert found.discipline_name == "Banco de Dados"
        assert found.professor_id == member.id
        assert found.room_id == room.id
        assert found.deleted is False

    async def test_list_by_tenant_excludes_deleted(self, session):
        """Deve listar apenas turmas ativas da instituição no repositório SQLAlchemy, excluindo as marcadas com soft delete."""
        user = await UserFactory.create(session)
        tenant = await TenantFactory.create(session)
        member = await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=user.id, role=UserRole.PROFESSOR
        )
        room_repo = RoomSQLAlchemyRepository(session)
        room = await room_repo.save(
            Room(tenant_id=tenant.id, name="Sala 102", latitude=-8.0, longitude=-34.0)
        )

        repo = SubjectClassSQLAlchemyRepository(session)

        sc1 = await repo.save(
            SubjectClass(
                tenant_id=tenant.id,
                professor_id=member.id,
                room_id=room.id,
                name="Turma A",
                discipline_name="D1",
            )
        )
        sc2 = await repo.save(
            SubjectClass(
                tenant_id=tenant.id,
                professor_id=member.id,
                room_id=room.id,
                name="Turma B",
                discipline_name="D2",
                deleted=True,
            )
        )

        active_list = await repo.list_by_tenant(tenant.id)
        assert len(active_list) == 1
        assert active_list[0].id == sc1.id

        all_list = await repo.list_by_tenant(tenant.id, include_deleted=True)
        assert len(all_list) == 2

    async def test_soft_delete(self, session):
        """Deve atualizar a flag deleted=True no banco de dados e ocultar o registro nas buscas normais."""
        user = await UserFactory.create(session)
        tenant = await TenantFactory.create(session)
        member = await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=user.id, role=UserRole.PROFESSOR
        )
        room_repo = RoomSQLAlchemyRepository(session)
        room = await room_repo.save(
            Room(tenant_id=tenant.id, name="Sala 103", latitude=-8.0, longitude=-34.0)
        )

        repo = SubjectClassSQLAlchemyRepository(session)
        sc = await repo.save(
            SubjectClass(
                tenant_id=tenant.id,
                professor_id=member.id,
                room_id=room.id,
                name="Para Soft Delete",
                discipline_name="D1",
            )
        )

        await repo.delete(sc)

        # Sem include_deleted -> None
        assert await repo.find_by_id(sc.id) is None
        assert await repo.find_by_id_and_tenant(sc.id, tenant.id) is None

        # Com include_deleted -> Registro com deleted=True
        deleted_sc = await repo.find_by_id(sc.id, include_deleted=True)
        assert deleted_sc is not None
        assert deleted_sc.deleted is True

    async def test_list_summaries_by_tenant_aggregates_students_and_attendance(self, session):
        """Listagem agrega nome do professor, alunos ativos e taxa de presença em uma query."""
        professor = await UserFactory.create(session, name="Ana Silva")
        tenant = await TenantFactory.create(session)
        prof_member = await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=professor.id, role=UserRole.PROFESSOR
        )

        student_a = await UserFactory.create(session, name="Aluno A")
        student_b = await UserFactory.create(session, name="Aluno B")
        student_dropped = await UserFactory.create(session, name="Aluno Dropped")
        member_a = await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=student_a.id, role=UserRole.ALUNO
        )
        member_b = await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=student_b.id, role=UserRole.ALUNO
        )
        member_dropped = await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=student_dropped.id, role=UserRole.ALUNO
        )

        room = await RoomSQLAlchemyRepository(session).save(
            Room(tenant_id=tenant.id, name="Sala 201", latitude=-8.0, longitude=-34.0)
        )
        repo = SubjectClassSQLAlchemyRepository(session)
        sc = await repo.save(
            SubjectClass(
                tenant_id=tenant.id,
                professor_id=prof_member.id,
                room_id=room.id,
                name="Turma Agregada",
                discipline_name="POO",
            )
        )
        empty = await repo.save(
            SubjectClass(
                tenant_id=tenant.id,
                professor_id=prof_member.id,
                room_id=room.id,
                name="Turma Vazia",
                discipline_name="Cálculo",
            )
        )

        enrollment_repo = EnrollmentSQLAlchemyRepository(session)
        await enrollment_repo.save(Enrollment(subject_class_id=sc.id, tenant_member_id=member_a.id))
        await enrollment_repo.save(Enrollment(subject_class_id=sc.id, tenant_member_id=member_b.id))
        await enrollment_repo.save(
            Enrollment(
                subject_class_id=sc.id,
                tenant_member_id=member_dropped.id,
                status=EnrollmentStatus.DROPPED,
            )
        )

        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
        session_repo = SessionSQLAlchemyRepository(session)
        closed_session = await session_repo.save(
            AttendanceSession(
                subject_class_id=sc.id,
                room_id=room.id,
                day_code="ABC123",
                expires_at=expires_at,
                status=SessionStatus.CLOSED,
                closed_at=datetime.now(timezone.utc),
            )
        )
        await session_repo.save(
            AttendanceSession(
                subject_class_id=sc.id,
                room_id=room.id,
                day_code="ZZZ999",
                expires_at=expires_at,
                status=SessionStatus.CANCELLED,
                closed_at=datetime.now(timezone.utc),
            )
        )

        record_repo = RecordSQLAlchemyRepository(session)
        await record_repo.save(
            AttendanceRecord(
                session_id=closed_session.id,
                tenant_member_id=member_a.id,
                latitude=-8.0,
                longitude=-34.0,
                distance_meters=1.0,
                within_radius=True,
                record_status=RecordStatus.REGULAR,
            )
        )
        await record_repo.save(
            AttendanceRecord(
                session_id=closed_session.id,
                tenant_member_id=member_b.id,
                latitude=-8.0,
                longitude=-34.0,
                distance_meters=1.0,
                within_radius=True,
                record_status=RecordStatus.IRREGULAR,
            )
        )
        await record_repo.save(
            AttendanceRecord(
                session_id=closed_session.id,
                tenant_member_id=member_dropped.id,
                latitude=-8.0,
                longitude=-34.0,
                distance_meters=1.0,
                within_radius=True,
                record_status=RecordStatus.REGULAR,
            )
        )

        summaries = await repo.list_summaries_by_tenant(tenant.id)
        by_id = {item.id: item for item in summaries}

        aggregated = by_id[sc.id]
        assert aggregated.professor_name == "Ana Silva"
        assert aggregated.student_count == 2
        assert aggregated.attendance_rate == 0.5

        vacant = by_id[empty.id]
        assert vacant.professor_name == "Ana Silva"
        assert vacant.student_count == 0
        assert vacant.attendance_rate == 0.0

    async def test_list_summaries_by_tenant_filters_by_professor_id(self, session):
        """Deve retornar apenas turmas do professor responsável informado."""
        tenant = await TenantFactory.create(session)
        prof_a = await UserFactory.create(session, name="Prof A")
        prof_b = await UserFactory.create(session, name="Prof B")
        member_a = await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=prof_a.id, role=UserRole.PROFESSOR
        )
        member_b = await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=prof_b.id, role=UserRole.PROFESSOR
        )
        room = await RoomSQLAlchemyRepository(session).save(
            Room(tenant_id=tenant.id, name="Sala Filtro", latitude=-8.0, longitude=-34.0)
        )
        repo = SubjectClassSQLAlchemyRepository(session)
        class_a = await repo.save(
            SubjectClass(
                tenant_id=tenant.id,
                professor_id=member_a.id,
                room_id=room.id,
                name="Turma A",
                discipline_name="POO",
            )
        )
        await repo.save(
            SubjectClass(
                tenant_id=tenant.id,
                professor_id=member_b.id,
                room_id=room.id,
                name="Turma B",
                discipline_name="Cálculo",
            )
        )

        summaries = await repo.list_summaries_by_tenant(tenant.id, professor_id=member_a.id)
        assert len(summaries) == 1
        assert summaries[0].id == class_a.id
        assert summaries[0].professor_id == member_a.id
        assert summaries[0].professor_name == "Prof A"

    async def test_list_summaries_by_tenant_filters_by_room_id(self, session):
        """Deve retornar apenas turmas vinculadas à sala informada."""
        tenant = await TenantFactory.create(session)
        professor = await UserFactory.create(session, name="Prof Sala")
        member = await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=professor.id, role=UserRole.PROFESSOR
        )
        room_repo = RoomSQLAlchemyRepository(session)
        room_a = await room_repo.save(
            Room(tenant_id=tenant.id, name="Sala A", latitude=-8.0, longitude=-34.0)
        )
        room_b = await room_repo.save(
            Room(tenant_id=tenant.id, name="Sala B", latitude=-8.1, longitude=-34.1)
        )
        repo = SubjectClassSQLAlchemyRepository(session)
        class_a = await repo.save(
            SubjectClass(
                tenant_id=tenant.id,
                professor_id=member.id,
                room_id=room_a.id,
                name="Turma Sala A",
                discipline_name="POO",
            )
        )
        await repo.save(
            SubjectClass(
                tenant_id=tenant.id,
                professor_id=member.id,
                room_id=room_b.id,
                name="Turma Sala B",
                discipline_name="Cálculo",
            )
        )

        all_summaries = await repo.list_summaries_by_tenant(tenant.id)
        assert len(all_summaries) == 2

        summaries = await repo.list_summaries_by_tenant(tenant.id, room_id=room_a.id)
        assert len(summaries) == 1
        assert summaries[0].id == class_a.id
        assert summaries[0].room_id == room_a.id
        assert summaries[0].name == "Turma Sala A"
        assert summaries[0].professor_name == "Prof Sala"

    async def test_find_summaries_by_tenant_paginated(self, session):
        """Deve retornar os resumos paginados de turmas por tenant, suportando busca por nome/disciplina."""
        from shared.pagination import PaginationParams

        tenant = await TenantFactory.create(session)
        professor = await UserFactory.create(session, name="Prof Paginated")
        member = await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=professor.id, role=UserRole.PROFESSOR
        )
        room = await RoomSQLAlchemyRepository(session).save(
            Room(tenant_id=tenant.id, name="Sala P", latitude=-8.0, longitude=-34.0)
        )
        repo = SubjectClassSQLAlchemyRepository(session)
        await repo.save(
            SubjectClass(
                tenant_id=tenant.id,
                professor_id=member.id,
                room_id=room.id,
                name="Turma Alfa",
                discipline_name="Matemática 1",
            )
        )
        await repo.save(
            SubjectClass(
                tenant_id=tenant.id,
                professor_id=member.id,
                room_id=room.id,
                name="Turma Beta",
                discipline_name="Matemática 2",
            )
        )
        await repo.save(
            SubjectClass(
                tenant_id=tenant.id,
                professor_id=member.id,
                room_id=room.id,
                name="Turma Gama",
                discipline_name="Física 1",
            )
        )

        # Pagination page 1
        page1 = await repo.find_summaries_by_tenant_paginated(
            tenant_id=tenant.id,
            pagination=PaginationParams(page=1, page_size=2),
        )
        assert len(page1.items) == 2
        assert page1.total == 3
        assert page1.page == 1
        assert page1.page_size == 2
        assert page1.pages == 2

        # Search filter
        search_res = await repo.find_summaries_by_tenant_paginated(
            tenant_id=tenant.id,
            pagination=PaginationParams(page=1, page_size=10),
            search="Matemática",
        )
        assert len(search_res.items) == 2
        assert search_res.total == 2

    async def test_list_and_paginated_summaries_filter_by_active(self, session):
        """Deve filtrar turmas por status active no repositório SQLAlchemy."""
        user = await UserFactory.create(session)
        tenant = await TenantFactory.create(session)
        member = await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=user.id, role=UserRole.PROFESSOR
        )
        room_repo = RoomSQLAlchemyRepository(session)
        room = await room_repo.save(
            Room(tenant_id=tenant.id, name="Sala Act", latitude=-8.0, longitude=-34.0)
        )
        repo = SubjectClassSQLAlchemyRepository(session)

        sc_act = await repo.save(
            SubjectClass(
                tenant_id=tenant.id,
                professor_id=member.id,
                room_id=room.id,
                name="Turma Ativa",
                discipline_name="Ativa D",
                active=True,
            )
        )
        sc_inact = await repo.save(
            SubjectClass(
                tenant_id=tenant.id,
                professor_id=member.id,
                room_id=room.id,
                name="Turma Inativa",
                discipline_name="Inativa D",
                active=False,
            )
        )

        # list_by_tenant filter
        actives = await repo.list_by_tenant(tenant.id, active=True)
        assert len(actives) == 1
        assert actives[0].id == sc_act.id

        inactives = await repo.list_by_tenant(tenant.id, active=False)
        assert len(inactives) == 1
        assert inactives[0].id == sc_inact.id

        # find_summaries_by_tenant_paginated filter
        page_act = await repo.find_summaries_by_tenant_paginated(
            tenant_id=tenant.id,
            pagination=PaginationParams(page=1, page_size=10),
            active=True,
        )
        assert page_act.total == 1
        assert page_act.items[0].id == sc_act.id
        assert page_act.items[0].active is True

        page_inact = await repo.find_summaries_by_tenant_paginated(
            tenant_id=tenant.id,
            pagination=PaginationParams(page=1, page_size=10),
            active=False,
        )
        assert page_inact.total == 1
        assert page_inact.items[0].id == sc_inact.id
        assert page_inact.items[0].active is False

    async def test_summaries_include_room_info_and_active_session_status(self, session):
        """Deve retornar informações completas da sala e indicar a presença de chamada ativa na turma."""
        tenant = await TenantFactory.create(session)
        user = await UserFactory.create(session, name="Prof Sessao")
        member = await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=user.id, role=UserRole.PROFESSOR
        )
        room_repo = RoomSQLAlchemyRepository(session)
        room = await room_repo.save(
            Room(tenant_id=tenant.id, name="Lab 305", latitude=-8.0, longitude=-34.0)
        )
        repo = SubjectClassSQLAlchemyRepository(session)
        session_repo = SessionSQLAlchemyRepository(session)

        # Turma 1: com sala e com sessão ativa (aberta e não expirada)
        sc_active_session = await repo.save(
            SubjectClass(
                tenant_id=tenant.id,
                professor_id=member.id,
                room_id=room.id,
                name="Turma Sessao Ativa",
                discipline_name="Sistemas",
            )
        )
        open_session = await session_repo.save(
            AttendanceSession(
                subject_class_id=sc_active_session.id,
                room_id=room.id,
                day_code="ACT123",
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
                status=SessionStatus.OPEN,
            )
        )

        # Turma 2: com sala e com sessão encerrada/fechada
        sc_closed_session = await repo.save(
            SubjectClass(
                tenant_id=tenant.id,
                professor_id=member.id,
                room_id=room.id,
                name="Turma Sessao Fechada",
                discipline_name="Redes",
            )
        )
        await session_repo.save(
            AttendanceSession(
                subject_class_id=sc_closed_session.id,
                room_id=room.id,
                day_code="CLS456",
                expires_at=datetime.now(timezone.utc) - timedelta(minutes=10),
                status=SessionStatus.CLOSED,
            )
        )

        # Turma 3: sem sala e sem sessão
        sc_no_room = await repo.save(
            SubjectClass(
                tenant_id=tenant.id,
                professor_id=member.id,
                room_id=None,
                name="Turma Sem Sala",
                discipline_name="Tópicos",
            )
        )

        # Consulta paginada
        page = await repo.find_summaries_by_tenant_paginated(
            tenant_id=tenant.id,
            pagination=PaginationParams(page=1, page_size=10),
        )
        summaries_by_id = {s.id: s for s in page.items}

        s1 = summaries_by_id[sc_active_session.id]
        assert s1.room_id == room.id
        assert s1.room_name == "Lab 305"
        assert s1.has_active_session is True
        assert s1.active_session_id == open_session.id

        s2 = summaries_by_id[sc_closed_session.id]
        assert s2.room_id == room.id
        assert s2.room_name == "Lab 305"
        assert s2.has_active_session is False
        assert s2.active_session_id is None

        s3 = summaries_by_id[sc_no_room.id]
        assert s3.room_id is None
        assert s3.room_name is None
        assert s3.has_active_session is False
        assert s3.active_session_id is None

        # Consulta não paginada (list_summaries_by_tenant)
        all_summaries = await repo.list_summaries_by_tenant(tenant.id)
        all_by_id = {s.id: s for s in all_summaries}
        assert all_by_id[sc_active_session.id].has_active_session is True
        assert all_by_id[sc_active_session.id].active_session_id == open_session.id
        assert all_by_id[sc_active_session.id].room_name == "Lab 305"
        assert all_by_id[sc_closed_session.id].has_active_session is False
        assert all_by_id[sc_no_room.id].room_name is None

    async def test_get_metrics_by_tenant(self, session):
        """Deve calcular métricas consolidadas de turmas corretamente no banco de dados."""
        user = await UserFactory.create(session, name="Prof Carlos")
        tenant = await TenantFactory.create(session)
        member = await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=user.id, role=UserRole.PROFESSOR
        )
        room_repo = RoomSQLAlchemyRepository(session)
        room = await room_repo.save(
            Room(tenant_id=tenant.id, name="Sala M", latitude=-8.0, longitude=-34.0)
        )
        repo = SubjectClassSQLAlchemyRepository(session)
        session_repo = SessionSQLAlchemyRepository(session)
        enrollment_repo = EnrollmentSQLAlchemyRepository(session)
        record_repo = RecordSQLAlchemyRepository(session)

        # Turma 1: ativa, 1 aluno, 1 sessão com 1 presença (100% de taxa)
        sc1 = await repo.save(
            SubjectClass(
                tenant_id=tenant.id,
                professor_id=member.id,
                room_id=room.id,
                name="Turma Metricas 1",
                discipline_name="Disc 1",
                active=True,
            )
        )
        student_user1 = await UserFactory.create(session)
        student_member1 = await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=student_user1.id, role=UserRole.ALUNO
        )
        await enrollment_repo.save(
            Enrollment(
                tenant_member_id=student_member1.id,
                subject_class_id=sc1.id,
            )
        )
        s1 = await session_repo.save(
            AttendanceSession(
                subject_class_id=sc1.id,
                room_id=room.id,
                day_code="MET1",
                expires_at=datetime.now(timezone.utc) - timedelta(minutes=10),
                status=SessionStatus.CLOSED,
            )
        )
        await record_repo.save(
            AttendanceRecord(
                session_id=s1.id,
                tenant_member_id=student_member1.id,
                latitude=-8.0,
                longitude=-34.0,
                distance_meters=5.0,
                within_radius=True,
                record_status=RecordStatus.REGULAR,
            )
        )

        # Turma 2: ativa, 1 aluno, 2 sessões e 0 presenças (0% de taxa -> em risco < 75%)
        # além disso, tem uma sessão aberta no momento (live)
        sc2 = await repo.save(
            SubjectClass(
                tenant_id=tenant.id,
                professor_id=member.id,
                room_id=room.id,
                name="Turma Metricas 2",
                discipline_name="Disc 2",
                active=True,
            )
        )
        student_user2 = await UserFactory.create(session)
        student_member2 = await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=student_user2.id, role=UserRole.ALUNO
        )
        await enrollment_repo.save(
            Enrollment(
                tenant_member_id=student_member2.id,
                subject_class_id=sc2.id,
            )
        )
        # Sessão passada sem presença
        await session_repo.save(
            AttendanceSession(
                subject_class_id=sc2.id,
                room_id=room.id,
                day_code="MET2A",
                expires_at=datetime.now(timezone.utc) - timedelta(days=1),
                status=SessionStatus.CLOSED,
            )
        )
        # Sessão ativa aberta agora
        await session_repo.save(
            AttendanceSession(
                subject_class_id=sc2.id,
                room_id=room.id,
                day_code="MET2B",
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
                status=SessionStatus.OPEN,
            )
        )

        # Turma 3: inativa
        sc3 = await repo.save(
            SubjectClass(
                tenant_id=tenant.id,
                professor_id=member.id,
                room_id=room.id,
                name="Turma Metricas 3",
                discipline_name="Disc 3",
                active=False,
            )
        )

        metrics = await repo.get_metrics_by_tenant(tenant.id)
        assert metrics.total_classes == 3
        assert metrics.active_classes == 2
        assert metrics.inactive_classes == 1
        assert metrics.total_students == 2
        # sc1 = 1.0 (1/1), sc2 = 0.0 (0/2) -> média das 2 ativas = 0.5
        assert metrics.average_attendance_rate == 0.5
        # sc2 tem taxa 0.0 < 0.75 -> 1 turma em risco
        assert metrics.at_risk_classes_count == 1
        # sc2 tem sessão aberta agora -> 1 turma ao vivo
        assert metrics.live_classes_count == 1

    async def test_find_summaries_search_by_professor_and_room(self, session):
        """Busca em find_summaries_by_tenant_paginated deve encontrar por nome de professor e sala."""
        prof1 = await UserFactory.create(session, name="Professora Beatriz")
        prof2 = await UserFactory.create(session, name="Professor Marcos")
        tenant = await TenantFactory.create(session)
        member1 = await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=prof1.id, role=UserRole.PROFESSOR
        )
        member2 = await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=prof2.id, role=UserRole.PROFESSOR
        )
        room_repo = RoomSQLAlchemyRepository(session)
        room_auditorio = await room_repo.save(
            Room(tenant_id=tenant.id, name="Auditório Principal", latitude=-8.0, longitude=-34.0)
        )
        room_lab = await room_repo.save(
            Room(tenant_id=tenant.id, name="Laboratório 202", latitude=-8.0, longitude=-34.0)
        )
        repo = SubjectClassSQLAlchemyRepository(session)

        sc1 = await repo.save(
            SubjectClass(
                tenant_id=tenant.id,
                professor_id=member1.id,
                room_id=room_lab.id,
                name="Turma Bio",
                discipline_name="Biologia Geral",
            )
        )
        sc2 = await repo.save(
            SubjectClass(
                tenant_id=tenant.id,
                professor_id=member2.id,
                room_id=room_auditorio.id,
                name="Turma Hist",
                discipline_name="História Moderna",
            )
        )

        # 1. Busca por nome do professor: "Beatriz"
        page_prof = await repo.find_summaries_by_tenant_paginated(
            tenant_id=tenant.id,
            pagination=PaginationParams(page=1, page_size=10),
            search="Beatriz",
        )
        assert page_prof.total == 1
        assert page_prof.items[0].id == sc1.id

        # 2. Busca por nome da sala: "Auditório"
        page_room = await repo.find_summaries_by_tenant_paginated(
            tenant_id=tenant.id,
            pagination=PaginationParams(page=1, page_size=10),
            search="Auditório",
        )
        assert page_room.total == 1
        assert page_room.items[0].id == sc2.id

    async def test_find_summaries_filter_has_active_session(self, session):
        """Filtro has_active_session deve retornar apenas turmas com ou sem sessão ativa."""
        user = await UserFactory.create(session)
        tenant = await TenantFactory.create(session)
        member = await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=user.id, role=UserRole.PROFESSOR
        )
        room_repo = RoomSQLAlchemyRepository(session)
        room = await room_repo.save(
            Room(tenant_id=tenant.id, name="Sala Live", latitude=-8.0, longitude=-34.0)
        )
        repo = SubjectClassSQLAlchemyRepository(session)
        session_repo = SessionSQLAlchemyRepository(session)

        sc_live = await repo.save(
            SubjectClass(
                tenant_id=tenant.id,
                professor_id=member.id,
                room_id=room.id,
                name="Turma Com Sessao Aberta",
                discipline_name="Ao Vivo",
            )
        )
        await session_repo.save(
            AttendanceSession(
                subject_class_id=sc_live.id,
                room_id=room.id,
                day_code="LIVE99",
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=25),
                status=SessionStatus.OPEN,
            )
        )

        sc_quiet = await repo.save(
            SubjectClass(
                tenant_id=tenant.id,
                professor_id=member.id,
                room_id=room.id,
                name="Turma Sem Chamada",
                discipline_name="Offline",
            )
        )

        # Filtro has_active_session=True
        page_live = await repo.find_summaries_by_tenant_paginated(
            tenant_id=tenant.id,
            pagination=PaginationParams(page=1, page_size=10),
            has_active_session=True,
        )
        assert page_live.total == 1
        assert page_live.items[0].id == sc_live.id

        # Filtro has_active_session=False
        page_quiet = await repo.find_summaries_by_tenant_paginated(
            tenant_id=tenant.id,
            pagination=PaginationParams(page=1, page_size=10),
            has_active_session=False,
        )
        assert page_quiet.total == 1
        assert page_quiet.items[0].id == sc_quiet.id

    async def test_find_summaries_sorting(self, session):
        """Deve suportar ordenação por nome e outros campos em find_summaries_by_tenant_paginated."""
        user = await UserFactory.create(session)
        tenant = await TenantFactory.create(session)
        member = await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=user.id, role=UserRole.PROFESSOR
        )
        repo = SubjectClassSQLAlchemyRepository(session)

        await repo.save(
            SubjectClass(
                tenant_id=tenant.id,
                professor_id=member.id,
                room_id=None,
                name="Alfa",
                discipline_name="D1",
            )
        )
        await repo.save(
            SubjectClass(
                tenant_id=tenant.id,
                professor_id=member.id,
                room_id=None,
                name="Zeta",
                discipline_name="D2",
            )
        )

        # Sort por nome asc
        page_asc = await repo.find_summaries_by_tenant_paginated(
            tenant_id=tenant.id,
            pagination=PaginationParams(page=1, page_size=10),
            sort_by="name",
            order="asc",
        )
        assert page_asc.items[0].name == "Alfa"
        assert page_asc.items[1].name == "Zeta"

        # Sort por nome desc (ou name_desc)
        page_desc = await repo.find_summaries_by_tenant_paginated(
            tenant_id=tenant.id,
            pagination=PaginationParams(page=1, page_size=10),
            sort_by="name_desc",
        )
        assert page_desc.items[0].name == "Zeta"
        assert page_desc.items[1].name == "Alfa"

