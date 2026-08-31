import pytest

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
