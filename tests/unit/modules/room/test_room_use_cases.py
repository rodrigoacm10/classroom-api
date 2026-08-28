from uuid import uuid4

import pytest

from modules.room.application.use_cases.create_room import CreateRoomInput, CreateRoomUseCase
from modules.room.application.use_cases.delete_room import DeleteRoomInput, DeleteRoomUseCase
from modules.room.application.use_cases.get_room import GetRoomInput, GetRoomUseCase
from modules.room.application.use_cases.list_rooms import ListRoomsInput, ListRoomsUseCase
from modules.room.application.use_cases.update_room import UpdateRoomInput, UpdateRoomUseCase
from modules.room.domain.entities.room import Room
from shared.exceptions import ResourceNotFoundException
from tests.factories.tenant_factory import TenantFactory
from tests.unit.fakes.fake_room_repository import FakeRoomRepository
from tests.unit.fakes.fake_tenant_repository import FakeTenantRepository


class TestRoomEntity:
    def test_is_within_radius_inside(self):
        """Deve retornar True quando o ponto está dentro do raio de tolerância (ex: ~15 metros de distância)."""
        room = Room(
            tenant_id=uuid4(),
            name="Lab 101",
            latitude=-8.047600,
            longitude=-34.877000,
            tolerance_radius_meters=50,
        )
        # Ponto muito próximo (~15m de distância)
        assert room.is_within_radius(latitude=-8.047610, longitude=-34.877010) is True

    def test_is_within_radius_outside(self):
        """Deve retornar False quando o ponto está bem fora do raio de tolerância (ex: ~1km de distância)."""
        room = Room(
            tenant_id=uuid4(),
            name="Lab 101",
            latitude=-8.047600,
            longitude=-34.877000,
            tolerance_radius_meters=50,
        )
        # Ponto distante (~1km)
        assert room.is_within_radius(latitude=-8.056000, longitude=-34.877000) is False


@pytest.mark.asyncio
class TestCreateRoomUseCase:
    async def test_create_room_success(self):
        """Deve criar uma sala com coordenadas geográficas e raio de tolerância."""
        room_repo = FakeRoomRepository()
        tenant_repo = FakeTenantRepository()

        tenant = TenantFactory.make()
        tenant_repo.seed(tenant)

        use_case = CreateRoomUseCase(room_repo=room_repo, tenant_repo=tenant_repo)
        room = await use_case.execute(
            CreateRoomInput(
                tenant_id=tenant.id,
                name="Auditório Principal",
                latitude=-8.0476,
                longitude=-34.8770,
                tolerance_radius_meters=100,
            )
        )

        assert room.name == "Auditório Principal"
        assert room.latitude == -8.0476
        assert room.longitude == -34.8770
        assert room.tolerance_radius_meters == 100
        assert room.tenant_id == tenant.id

    async def test_create_room_raises_when_tenant_not_found(self):
        """Deve lançar ResourceNotFoundException quando a tenant não existe."""
        room_repo = FakeRoomRepository()
        tenant_repo = FakeTenantRepository()

        use_case = CreateRoomUseCase(room_repo=room_repo, tenant_repo=tenant_repo)
        with pytest.raises(ResourceNotFoundException):
            await use_case.execute(
                CreateRoomInput(
                    tenant_id=uuid4(),
                    name="Sala 1",
                    latitude=-8.0,
                    longitude=-34.0,
                )
            )

    async def test_create_room_raises_when_tenant_is_deleted(self):
        """Deve lançar ResourceNotFoundException quando a tenant está deletada."""
        room_repo = FakeRoomRepository()
        tenant_repo = FakeTenantRepository()

        tenant = TenantFactory.make(deleted=True)
        tenant_repo.seed(tenant)

        use_case = CreateRoomUseCase(room_repo=room_repo, tenant_repo=tenant_repo)
        with pytest.raises(ResourceNotFoundException):
            await use_case.execute(
                CreateRoomInput(
                    tenant_id=tenant.id,
                    name="Sala 1",
                    latitude=-8.0,
                    longitude=-34.0,
                )
            )


@pytest.mark.asyncio
class TestGetRoomUseCase:
    async def test_get_room_success(self):
        """Deve retornar os detalhes da sala quando o ID e tenant conferem."""
        room_repo = FakeRoomRepository()
        tenant_id = uuid4()

        room = Room(
            tenant_id=tenant_id,
            name="Sala 204",
            latitude=-8.0476,
            longitude=-34.8770,
        )
        await room_repo.save(room)

        use_case = GetRoomUseCase(room_repo=room_repo)
        result = await use_case.execute(GetRoomInput(room_id=room.id, tenant_id=tenant_id))

        assert result.id == room.id
        assert result.name == "Sala 204"

    async def test_get_room_raises_when_not_found(self):
        """Deve lançar ResourceNotFoundException quando a sala não é encontrada."""
        room_repo = FakeRoomRepository()
        use_case = GetRoomUseCase(room_repo=room_repo)

        with pytest.raises(ResourceNotFoundException):
            await use_case.execute(GetRoomInput(room_id=uuid4(), tenant_id=uuid4()))

    async def test_get_room_raises_when_deleted(self):
        """Deve lançar ResourceNotFoundException ao tentar obter uma sala deletada (soft delete)."""
        room_repo = FakeRoomRepository()
        tenant_id = uuid4()

        room = Room(
            tenant_id=tenant_id,
            name="Sala Deletada",
            latitude=-8.0,
            longitude=-34.0,
            deleted=True,
        )
        await room_repo.save(room)

        use_case = GetRoomUseCase(room_repo=room_repo)
        with pytest.raises(ResourceNotFoundException):
            await use_case.execute(GetRoomInput(room_id=room.id, tenant_id=tenant_id))


@pytest.mark.asyncio
class TestListRoomsUseCase:
    async def test_list_rooms_success(self):
        """Deve listar todas as salas pertencentes à tenant especificada."""
        room_repo = FakeRoomRepository()
        tenant_repo = FakeTenantRepository()

        tenant1 = TenantFactory.make()
        tenant2 = TenantFactory.make()
        tenant_repo.seed(tenant1)
        tenant_repo.seed(tenant2)

        room1 = Room(tenant_id=tenant1.id, name="Sala A", latitude=0.0, longitude=0.0)
        room2 = Room(tenant_id=tenant1.id, name="Sala B", latitude=0.0, longitude=0.0)
        room3 = Room(tenant_id=tenant2.id, name="Sala C", latitude=0.0, longitude=0.0)
        await room_repo.save(room1)
        await room_repo.save(room2)
        await room_repo.save(room3)

        use_case = ListRoomsUseCase(room_repo=room_repo, tenant_repo=tenant_repo)
        result = await use_case.execute(ListRoomsInput(tenant_id=tenant1.id))

        assert len(result) == 2
        names = [r.name for r in result]
        assert "Sala A" in names
        assert "Sala B" in names
        assert "Sala C" not in names

    async def test_list_rooms_excludes_deleted_rooms(self):
        """Deve excluir salas marcadas com deleted=True da listagem."""
        room_repo = FakeRoomRepository()
        tenant_repo = FakeTenantRepository()

        tenant = TenantFactory.make()
        tenant_repo.seed(tenant)

        room_active = Room(tenant_id=tenant.id, name="Sala Ativa", latitude=0.0, longitude=0.0, deleted=False)
        room_deleted = Room(tenant_id=tenant.id, name="Sala Deletada", latitude=0.0, longitude=0.0, deleted=True)
        await room_repo.save(room_active)
        await room_repo.save(room_deleted)

        use_case = ListRoomsUseCase(room_repo=room_repo, tenant_repo=tenant_repo)
        result = await use_case.execute(ListRoomsInput(tenant_id=tenant.id))

        assert len(result) == 1
        assert result[0].name == "Sala Ativa"

    async def test_list_rooms_raises_when_tenant_not_found(self):
        """Deve lançar ResourceNotFoundException quando a tenant não existe."""
        room_repo = FakeRoomRepository()
        tenant_repo = FakeTenantRepository()

        use_case = ListRoomsUseCase(room_repo=room_repo, tenant_repo=tenant_repo)
        with pytest.raises(ResourceNotFoundException):
            await use_case.execute(ListRoomsInput(tenant_id=uuid4()))

    async def test_list_rooms_raises_when_tenant_is_deleted(self):
        """Deve lançar ResourceNotFoundException quando a tenant está deletada."""
        room_repo = FakeRoomRepository()
        tenant_repo = FakeTenantRepository()

        tenant = TenantFactory.make(deleted=True)
        tenant_repo.seed(tenant)

        use_case = ListRoomsUseCase(room_repo=room_repo, tenant_repo=tenant_repo)
        with pytest.raises(ResourceNotFoundException):
            await use_case.execute(ListRoomsInput(tenant_id=tenant.id))


@pytest.mark.asyncio
class TestUpdateRoomUseCase:
    async def test_update_room_patch_fields(self):
        """Deve atualizar apenas os campos informados (PATCH semântico)."""
        room_repo = FakeRoomRepository()
        tenant_id = uuid4()

        room = Room(
            tenant_id=tenant_id,
            name="Sala Antiga",
            latitude=-8.0476,
            longitude=-34.8770,
            tolerance_radius_meters=30,
        )
        await room_repo.save(room)

        use_case = UpdateRoomUseCase(room_repo=room_repo)
        updated = await use_case.execute(
            UpdateRoomInput(
                room_id=room.id,
                tenant_id=tenant_id,
                name="Sala Nova",
                tolerance_radius_meters=75,
            )
        )

        assert updated.name == "Sala Nova"
        assert updated.tolerance_radius_meters == 75
        assert updated.latitude == -8.0476
        assert updated.longitude == -34.8770

    async def test_update_room_raises_when_not_found(self):
        """Deve lançar ResourceNotFoundException ao tentar atualizar sala inexistente."""
        room_repo = FakeRoomRepository()
        use_case = UpdateRoomUseCase(room_repo=room_repo)

        with pytest.raises(ResourceNotFoundException):
            await use_case.execute(
                UpdateRoomInput(
                    room_id=uuid4(),
                    tenant_id=uuid4(),
                    name="Novo Nome",
                )
            )

    async def test_update_room_raises_when_deleted(self):
        """Deve lançar ResourceNotFoundException ao tentar atualizar uma sala deletada (soft delete)."""
        room_repo = FakeRoomRepository()
        tenant_id = uuid4()

        room = Room(
            tenant_id=tenant_id,
            name="Sala Deletada",
            latitude=-8.0,
            longitude=-34.0,
            deleted=True,
        )
        await room_repo.save(room)

        use_case = UpdateRoomUseCase(room_repo=room_repo)
        with pytest.raises(ResourceNotFoundException):
            await use_case.execute(
                UpdateRoomInput(
                    room_id=room.id,
                    tenant_id=tenant_id,
                    name="Novo Nome",
                )
            )


@pytest.mark.asyncio
class TestDeleteRoomUseCase:
    async def test_soft_delete_room_success(self):
        """Deve realizar o soft delete da sala alterando a flag deleted para True."""
        room_repo = FakeRoomRepository()
        tenant_id = uuid4()

        room = Room(
            tenant_id=tenant_id,
            name="Sala Temp",
            latitude=0.0,
            longitude=0.0,
            deleted=False,
        )
        await room_repo.save(room)

        use_case = DeleteRoomUseCase(room_repo=room_repo)
        await use_case.execute(DeleteRoomInput(room_id=room.id, tenant_id=tenant_id))

        # Busca normal não encontra a sala
        found_active = await room_repo.find_by_id(room.id)
        assert found_active is None

        # Busca incluindo deletados encontra a sala marcada com deleted=True
        found_deleted = await room_repo.find_by_id(room.id, include_deleted=True)
        assert found_deleted is not None
        assert found_deleted.deleted is True

    async def test_delete_room_raises_when_not_found(self):
        """Deve lançar ResourceNotFoundException ao tentar deletar sala inexistente."""
        room_repo = FakeRoomRepository()
        use_case = DeleteRoomUseCase(room_repo=room_repo)

        with pytest.raises(ResourceNotFoundException):
            await use_case.execute(DeleteRoomInput(room_id=uuid4(), tenant_id=uuid4()))
