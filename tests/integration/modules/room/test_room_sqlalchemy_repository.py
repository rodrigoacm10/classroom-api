import uuid

import pytest

from modules.room.domain.entities.room import Room
from modules.room.infra.repositories.room_sqlalchemy_repository import (
    RoomSQLAlchemyRepository,
)
from tests.factories.tenant_factory import TenantFactory


@pytest.mark.asyncio
class TestRoomSQLAlchemyRepository:
    """
    Testes de integração para RoomSQLAlchemyRepository com PostGIS no PostgreSQL real.
    """

    @pytest.fixture(autouse=True)
    def setup(self, session) -> None:
        self.repository = RoomSQLAlchemyRepository(session=session)
        self.session = session

    async def test_save_and_find_by_id_with_postgis_coordinates(self) -> None:
        """Persiste uma sala no PostGIS com GEOGRAPHY Point e recupera latitude/longitude corretamente."""
        tenant = await TenantFactory.create(self.session)

        room = Room(
            tenant_id=tenant.id,
            name="Lab de Informática 3",
            latitude=-8.047600,
            longitude=-34.877000,
            tolerance_radius_meters=45,
        )

        saved = await self.repository.save(room)
        assert saved.id == room.id
        assert saved.name == "Lab de Informática 3"
        assert saved.latitude == pytest.approx(-8.047600)
        assert saved.longitude == pytest.approx(-34.877000)
        assert saved.tolerance_radius_meters == 45

        found = await self.repository.find_by_id_and_tenant(room.id, tenant.id)
        assert found is not None
        assert found.id == room.id
        assert found.name == "Lab de Informática 3"
        assert found.latitude == pytest.approx(-8.047600)
        assert found.longitude == pytest.approx(-34.877000)

    async def test_list_by_tenant_filters_correctly(self) -> None:
        """list_by_tenant deve retornar apenas as salas pertencentes à tenant."""
        tenant1 = await TenantFactory.create(self.session)
        tenant2 = await TenantFactory.create(self.session)

        room1 = Room(tenant_id=tenant1.id, name="Sala T1-A", latitude=-8.0, longitude=-34.0)
        room2 = Room(tenant_id=tenant1.id, name="Sala T1-B", latitude=-8.0, longitude=-34.0)
        room3 = Room(tenant_id=tenant2.id, name="Sala T2-A", latitude=-8.0, longitude=-34.0)

        await self.repository.save(room1)
        await self.repository.save(room2)
        await self.repository.save(room3)

        rooms_t1 = await self.repository.list_by_tenant(tenant1.id)
        assert len(rooms_t1) == 2
        names_t1 = [r.name for r in rooms_t1]
        assert "Sala T1-A" in names_t1
        assert "Sala T1-B" in names_t1
        assert "Sala T2-A" not in names_t1

    async def test_soft_delete_room_and_filtering(self) -> None:
        """delete deve realizar soft delete (deleted=True) e ocultar a sala de buscas normais."""
        tenant = await TenantFactory.create(self.session)
        room = Room(tenant_id=tenant.id, name="Sala Excluível", latitude=-8.0, longitude=-34.0, deleted=False)

        await self.repository.save(room)
        await self.repository.delete(room)

        # Busca normal ignora deletados
        found_active = await self.repository.find_by_id(room.id)
        assert found_active is None

        # Listagem normal ignora deletados
        rooms_active = await self.repository.list_by_tenant(tenant.id)
        assert len(rooms_active) == 0

        # Busca com include_deleted=True encontra a sala
        found_deleted = await self.repository.find_by_id(room.id, include_deleted=True)
        assert found_deleted is not None
        assert found_deleted.deleted is True

