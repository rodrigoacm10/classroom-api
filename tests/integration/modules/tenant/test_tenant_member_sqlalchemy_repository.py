import pytest
from sqlalchemy.exc import IntegrityError

from modules.tenant.domain.entities.tenant_member import TenantMember
from modules.tenant.infra.repositories.tenant_member_sqlalchemy_repository import (
    TenantMemberSQLAlchemyRepository,
)
from shared.enums.user_role import UserRole
from tests.factories.tenant_factory import TenantFactory
from tests.factories.user_factory import UserFactory


@pytest.mark.asyncio
class TestTenantMemberSQLAlchemyRepository:
    """
    Testes de integração para TenantMemberSQLAlchemyRepository no PostgreSQL real.
    Valida o comportamento do índice único parcial (uq_active_tenant_user).
    """

    @pytest.fixture(autouse=True)
    def setup(self, session) -> None:
        self.repository = TenantMemberSQLAlchemyRepository(session=session)
        self.session = session

    async def test_save_and_find_by_tenant_and_user(self) -> None:
        """Persiste um membro e realiza a busca no Postgres."""
        tenant = await TenantFactory.create(self.session)
        user = await UserFactory.create(self.session)

        member = TenantMember(tenant_id=tenant.id, user_id=user.id, role=UserRole.PROFESSOR)
        saved = await self.repository.save(member)

        assert saved.id == member.id
        assert saved.deleted is False

        found = await self.repository.find_by_tenant_and_user(tenant.id, user.id)
        assert found is not None
        assert found.id == member.id
        assert found.role == UserRole.PROFESSOR

    async def test_partial_unique_index_blocks_duplicate_active_members(self) -> None:
        """Tentar criar outro vínculo ATIVO para o mesmo usuário e tenant deve falhar (IntegrityError)."""
        tenant = await TenantFactory.create(self.session)
        user = await UserFactory.create(self.session)

        member_1 = TenantMember(tenant_id=tenant.id, user_id=user.id, role=UserRole.ALUNO)
        await self.repository.save(member_1)

        member_duplicate = TenantMember(tenant_id=tenant.id, user_id=user.id, role=UserRole.PROFESSOR)
        with pytest.raises(IntegrityError):
            await self.repository.save(member_duplicate)

    async def test_partial_unique_index_allows_recreation_after_soft_delete(self) -> None:
        """
        Valida que o índice único parcial 'uq_active_tenant_user' (WHERE deleted IS FALSE)
        PERMITE criar um novo registro ativo após o anterior ser marcado como deletado (Soft Delete).
        """
        tenant = await TenantFactory.create(self.session)
        user = await UserFactory.create(self.session)

        # 1. Cria primeiro vínculo e faz soft delete
        member_1 = TenantMember(tenant_id=tenant.id, user_id=user.id, role=UserRole.ALUNO)
        saved_1 = await self.repository.save(member_1)

        saved_1.deleted = True
        await self.repository.save(saved_1)

        # 2. Agora que o anterior está deleted=True, criar um NOVO registro ativo DEVE PASSAR com sucesso!
        member_2 = TenantMember(tenant_id=tenant.id, user_id=user.id, role=UserRole.PROFESSOR)
        saved_2 = await self.repository.save(member_2)

        assert saved_2.id != saved_1.id
        assert saved_2.role == UserRole.PROFESSOR
        assert saved_2.deleted is False

        # Consulta de membro ativo deve retornar o novo membro_2
        active_found = await self.repository.find_by_tenant_and_user(tenant.id, user.id, include_deleted=False)
        assert active_found is not None
        assert active_found.id == saved_2.id

    async def test_count_active_admins(self) -> None:
        """count_active_admins deve contar apenas administradores com deleted=False."""
        tenant = await TenantFactory.create(self.session)
        admin1 = await UserFactory.create(self.session)
        admin2 = await UserFactory.create(self.session)
        aluno = await UserFactory.create(self.session)

        # Popula banco
        m_admin1 = TenantMember(tenant_id=tenant.id, user_id=admin1.id, role=UserRole.ADMIN)
        m_admin2 = TenantMember(tenant_id=tenant.id, user_id=admin2.id, role=UserRole.ADMIN)
        m_aluno = TenantMember(tenant_id=tenant.id, user_id=aluno.id, role=UserRole.ALUNO)

        await self.repository.save(m_admin1)
        await self.repository.save(m_admin2)
        await self.repository.save(m_aluno)

        assert await self.repository.count_active_admins(tenant.id) == 2

        # Deleta um admin
        m_admin1.deleted = True
        await self.repository.save(m_admin1)

        # Agora deve restar apenas 1 admin ativo
        assert await self.repository.count_active_admins(tenant.id) == 1
