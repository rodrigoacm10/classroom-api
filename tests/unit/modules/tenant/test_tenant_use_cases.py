import pytest

from modules.tenant.application.use_cases.activate_tenant import ActivateTenantUseCase
from modules.tenant.application.use_cases.create_tenant import (
    CreateTenantInput,
    CreateTenantUseCase,
)
from modules.tenant.application.use_cases.deactivate_tenant import DeactivateTenantUseCase
from modules.tenant.application.use_cases.delete_tenant import DeleteTenantUseCase
from modules.tenant.application.use_cases.list_my_tenants import ListMyTenantsUseCase
from modules.tenant.domain.entities.tenant_member import TenantMember
from shared.enums.user_role import UserRole
from shared.exceptions import ResourceNotFoundException
from tests.factories.tenant_factory import TenantFactory
from tests.factories.user_factory import UserFactory
from tests.unit.fakes.fake_tenant_member_repository import FakeTenantMemberRepository
from tests.unit.fakes.fake_tenant_repository import FakeTenantRepository


@pytest.mark.asyncio
class TestCreateTenantUseCase:
    async def test_create_tenant_success(self):
        """Deve criar a tenant com sucesso e associar o criador como ADMIN."""
        tenant_repo = FakeTenantRepository()
        member_repo = FakeTenantMemberRepository()
        use_case = CreateTenantUseCase(tenant_repo=tenant_repo, member_repo=member_repo)

        user = UserFactory.make()
        result = await use_case.execute(
            CreateTenantInput(
                name="Escola Alpha",
                slug="escola-alpha",
                owner_user_id=str(user.id),
            )
        )

        assert result.tenant.name == "Escola Alpha"
        assert result.tenant.slug == "escola-alpha"
        assert result.tenant.active is True
        assert result.tenant.deleted is False
        assert result.member.role == UserRole.ADMIN


@pytest.mark.asyncio
class TestDeleteTenantUseCase:
    async def test_soft_delete_tenant_success(self):
        """Deve realizar o soft delete da tenant alterando a flag deleted para True."""
        tenant_repo = FakeTenantRepository()
        tenant = TenantFactory.make(active=True, deleted=False)
        tenant_repo.seed(tenant)

        use_case = DeleteTenantUseCase(tenant_repo=tenant_repo)
        deleted_tenant = await use_case.execute(tenant.id)

        assert deleted_tenant.deleted is True
        # Consulta normal deve retornar None agora que foi deletado
        found = await tenant_repo.find_by_id(tenant.id)
        assert found is None

    async def test_soft_delete_non_existent_tenant_raises_not_found(self):
        """Deve lançar ResourceNotFoundException ao tentar deletar tenant inexistente."""
        tenant_repo = FakeTenantRepository()
        use_case = DeleteTenantUseCase(tenant_repo=tenant_repo)

        dummy_tenant = TenantFactory.make()
        with pytest.raises(ResourceNotFoundException):
            await use_case.execute(dummy_tenant.id)


@pytest.mark.asyncio
class TestActivateTenantUseCase:
    async def test_activate_tenant_success(self):
        """Deve ativar a tenant alterando a flag active para True."""
        tenant_repo = FakeTenantRepository()
        tenant = TenantFactory.make(active=False, deleted=False)
        tenant_repo.seed(tenant)

        use_case = ActivateTenantUseCase(tenant_repo=tenant_repo)
        updated_tenant = await use_case.execute(tenant.id)

        assert updated_tenant.active is True

    async def test_activate_deleted_tenant_raises_not_found(self):
        """Deve lançar ResourceNotFoundException ao tentar ativar tenant deletada."""
        tenant_repo = FakeTenantRepository()
        tenant = TenantFactory.make(active=False, deleted=True)
        tenant_repo.seed(tenant)

        use_case = ActivateTenantUseCase(tenant_repo=tenant_repo)
        with pytest.raises(ResourceNotFoundException):
            await use_case.execute(tenant.id)


@pytest.mark.asyncio
class TestDeactivateTenantUseCase:
    async def test_deactivate_tenant_success(self):
        """Deve desativar a tenant alterando a flag active para False."""
        tenant_repo = FakeTenantRepository()
        tenant = TenantFactory.make(active=True, deleted=False)
        tenant_repo.seed(tenant)

        use_case = DeactivateTenantUseCase(tenant_repo=tenant_repo)
        updated_tenant = await use_case.execute(tenant.id)

        assert updated_tenant.active is False


@pytest.mark.asyncio
class TestListMyTenantsUseCase:
    async def test_list_my_tenants_excludes_deleted_tenants(self):
        """Deve listar apenas as tenants do usuário que não foram deletadas."""
        tenant_repo = FakeTenantRepository()
        member_repo = FakeTenantMemberRepository()
        user = UserFactory.make()

        active_tenant = TenantFactory.make(name="Active School", active=True, deleted=False)
        deleted_tenant = TenantFactory.make(name="Deleted School", active=True, deleted=True)

        tenant_repo.seed(active_tenant)
        tenant_repo.seed(deleted_tenant)

        member_repo.seed(
            TenantMember(tenant_id=active_tenant.id, user_id=user.id, role=UserRole.ADMIN)
        )
        member_repo.seed(
            TenantMember(tenant_id=deleted_tenant.id, user_id=user.id, role=UserRole.PROFESSOR)
        )

        use_case = ListMyTenantsUseCase(tenant_repo=tenant_repo, member_repo=member_repo)
        items = await use_case.execute(user.id)

        assert len(items) == 1
        assert items[0].tenant.id == active_tenant.id
        assert items[0].tenant.name == "Active School"


@pytest.mark.asyncio
class TestRemoveTenantMemberUseCase:
    async def test_remove_tenant_member_success(self):
        """Deve marcar o membro como deleted=True com sucesso."""
        from modules.tenant.application.use_cases.remove_tenant_member import (
            RemoveTenantMemberInput,
            RemoveTenantMemberUseCase,
        )

        tenant_repo = FakeTenantRepository()
        member_repo = FakeTenantMemberRepository()

        tenant = TenantFactory.make()
        tenant_repo.seed(tenant)

        admin = UserFactory.make()
        member_user = UserFactory.make()

        member_repo.seed(
            TenantMember(tenant_id=tenant.id, user_id=admin.id, role=UserRole.ADMIN)
        )
        member_to_remove = TenantMember(
            tenant_id=tenant.id, user_id=member_user.id, role=UserRole.PROFESSOR
        )
        member_repo.seed(member_to_remove)

        use_case = RemoveTenantMemberUseCase(tenant_repo=tenant_repo, member_repo=member_repo)
        removed = await use_case.execute(
            RemoveTenantMemberInput(
                tenant_id=tenant.id,
                user_id_to_remove=member_user.id,
            )
        )

        assert removed.deleted is True
        # Consulta normal de membro ativo deve retornar None agora
        found = await member_repo.find_by_tenant_and_user(tenant.id, member_user.id)
        assert found is None

    async def test_remove_single_admin_raises_business_rule_exception(self):
        """Deve proibir a remoção do único administrador da instituição."""
        from modules.tenant.application.use_cases.remove_tenant_member import (
            RemoveTenantMemberInput,
            RemoveTenantMemberUseCase,
        )
        from shared.exceptions import BusinessRuleException

        tenant_repo = FakeTenantRepository()
        member_repo = FakeTenantMemberRepository()

        tenant = TenantFactory.make()
        tenant_repo.seed(tenant)

        admin = UserFactory.make()
        member_repo.seed(
            TenantMember(tenant_id=tenant.id, user_id=admin.id, role=UserRole.ADMIN)
        )

        use_case = RemoveTenantMemberUseCase(tenant_repo=tenant_repo, member_repo=member_repo)

        with pytest.raises(BusinessRuleException, match="único administrador"):
            await use_case.execute(
                RemoveTenantMemberInput(
                    tenant_id=tenant.id,
                    user_id_to_remove=admin.id,
                )
            )

