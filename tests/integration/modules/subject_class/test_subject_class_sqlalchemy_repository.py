import pytest

from datetime import datetime, timedelta, timezone

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
from tests.factories.tenant_factory import TenantFactory
from tests.factories.user_factory import UserFactory


@pytest.mark.asyncio
class TestSubjectClassSQLAlchemyRepository:

    async def test_save_and_find_by_id(self, session):
        """Deve persistir uma turma no banco de dados e recuperá-la por ID com sucesso."""
        user = await UserFactory.create(session)
        tenant = await TenantFactory.create(session)
        member = await TenantFactory.create_member(session, tenant_id=tenant.id, user_id=user.id, role=UserRole.PROFESSOR)

        room_repo = RoomSQLAlchemyRepository(session)
        room = await room_repo.save(Room(tenant_id=tenant.id, name="Sala 101", latitude=-8.0, longitude=-34.0))

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
        member = await TenantFactory.create_member(session, tenant_id=tenant.id, user_id=user.id, role=UserRole.PROFESSOR)
        room_repo = RoomSQLAlchemyRepository(session)
        room = await room_repo.save(Room(tenant_id=tenant.id, name="Sala 102", latitude=-8.0, longitude=-34.0))

        repo = SubjectClassSQLAlchemyRepository(session)

        sc1 = await repo.save(SubjectClass(tenant_id=tenant.id, professor_id=member.id, room_id=room.id, name="Turma A", discipline_name="D1"))
        sc2 = await repo.save(SubjectClass(tenant_id=tenant.id, professor_id=member.id, room_id=room.id, name="Turma B", discipline_name="D2", deleted=True))

        active_list = await repo.list_by_tenant(tenant.id)
        assert len(active_list) == 1
        assert active_list[0].id == sc1.id

        all_list = await repo.list_by_tenant(tenant.id, include_deleted=True)
        assert len(all_list) == 2

    async def test_soft_delete(self, session):
        """Deve atualizar a flag deleted=True no banco de dados e ocultar o registro nas buscas normais."""
        user = await UserFactory.create(session)
        tenant = await TenantFactory.create(session)
        member = await TenantFactory.create_member(session, tenant_id=tenant.id, user_id=user.id, role=UserRole.PROFESSOR)
        room_repo = RoomSQLAlchemyRepository(session)
        room = await room_repo.save(Room(tenant_id=tenant.id, name="Sala 103", latitude=-8.0, longitude=-34.0))

        repo = SubjectClassSQLAlchemyRepository(session)
        sc = await repo.save(SubjectClass(tenant_id=tenant.id, professor_id=member.id, room_id=room.id, name="Para Soft Delete", discipline_name="D1"))

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
            SubjectClass(tenant_id=tenant.id, professor_id=member.id, room_id=room.id, name="Turma Alfa", discipline_name="Matemática 1")
        )
        await repo.save(
            SubjectClass(tenant_id=tenant.id, professor_id=member.id, room_id=room.id, name="Turma Beta", discipline_name="Matemática 2")
        )
        await repo.save(
            SubjectClass(tenant_id=tenant.id, professor_id=member.id, room_id=room.id, name="Turma Gama", discipline_name="Física 1")
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
