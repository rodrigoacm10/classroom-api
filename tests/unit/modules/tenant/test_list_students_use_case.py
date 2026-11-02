import uuid

import pytest

from modules.tenant.application.use_cases.list_students import (
    ListStudentsInput,
    ListStudentsUseCase,
)
from modules.tenant.domain.entities.tenant import Tenant
from modules.tenant.domain.entities.tenant_member import TenantMember
from shared.enums.user_role import UserRole
from shared.exceptions import ResourceNotFoundException
from shared.pagination import PaginationParams
from tests.unit.fakes.fake_tenant_member_repository import FakeTenantMemberRepository
from tests.unit.fakes.fake_tenant_repository import FakeTenantRepository


@pytest.mark.asyncio
class TestListStudentsUseCase:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.tenant_repo = FakeTenantRepository()
        self.member_repo = FakeTenantMemberRepository()
        self.use_case = ListStudentsUseCase(
            tenant_repo=self.tenant_repo,
            member_repo=self.member_repo,
        )

    async def test_list_students_returns_only_alunos(self):
        tenant = Tenant(name="Universidade Teste", slug="univ-teste")
        await self.tenant_repo.save(tenant)

        # 1 Admin, 1 Professor, 2 Alunos
        admin = TenantMember(
            tenant_id=tenant.id,
            user_id=uuid.uuid4(),
            role=UserRole.ADMIN,
            name="Admin User",
            email="admin@test.com",
        )
        prof = TenantMember(
            tenant_id=tenant.id,
            user_id=uuid.uuid4(),
            role=UserRole.PROFESSOR,
            name="Prof User",
            email="prof@test.com",
        )
        aluno1 = TenantMember(
            tenant_id=tenant.id,
            user_id=uuid.uuid4(),
            role=UserRole.ALUNO,
            name="Lucas Oliveira",
            email="lucas@aluno.com",
        )
        aluno2 = TenantMember(
            tenant_id=tenant.id,
            user_id=uuid.uuid4(),
            role=UserRole.ALUNO,
            name="Beatriz Santos",
            email="beatriz@aluno.com",
        )

        for m in [admin, prof, aluno1, aluno2]:
            await self.member_repo.save(m)

        result = await self.use_case.execute(
            ListStudentsInput(
                tenant_id=tenant.id, pagination=PaginationParams(page=1, page_size=10)
            )
        )

        assert result.total == 2
        assert len(result.items) == 2
        roles = {item.role for item in result.items}
        assert roles == {UserRole.ALUNO}
        names = {item.name for item in result.items}
        assert names == {"Lucas Oliveira", "Beatriz Santos"}

    async def test_list_students_filter_by_search(self):
        tenant = Tenant(name="Universidade Teste", slug="univ-teste")
        await self.tenant_repo.save(tenant)

        aluno1 = TenantMember(
            tenant_id=tenant.id,
            user_id=uuid.uuid4(),
            role=UserRole.ALUNO,
            name="Lucas Oliveira",
            email="lucas@aluno.com",
        )
        aluno2 = TenantMember(
            tenant_id=tenant.id,
            user_id=uuid.uuid4(),
            role=UserRole.ALUNO,
            name="Beatriz Santos",
            email="beatriz@aluno.com",
        )
        await self.member_repo.save(aluno1)
        await self.member_repo.save(aluno2)

        # Busca por nome
        res_name = await self.use_case.execute(
            ListStudentsInput(tenant_id=tenant.id, search="lucas")
        )
        assert res_name.total == 1
        assert res_name.items[0].name == "Lucas Oliveira"

        # Busca por e-mail
        res_email = await self.use_case.execute(
            ListStudentsInput(tenant_id=tenant.id, search="beatriz@aluno.com")
        )
        assert res_email.total == 1
        assert res_email.items[0].email == "beatriz@aluno.com"

    async def test_list_students_raises_when_tenant_not_found(self):
        with pytest.raises(ResourceNotFoundException):
            await self.use_case.execute(ListStudentsInput(tenant_id=uuid.uuid4()))

    async def test_list_students_filter_by_status(self):
        tenant = Tenant(name="Universidade Teste", slug="univ-teste")
        await self.tenant_repo.save(tenant)

        aluno_regular = TenantMember(
            tenant_id=tenant.id,
            user_id=uuid.uuid4(),
            role=UserRole.ALUNO,
            name="Aluno Regular",
            email="regular@aluno.com",
            turmas_count=2,
        )
        aluno_sem_turma = TenantMember(
            tenant_id=tenant.id,
            user_id=uuid.uuid4(),
            role=UserRole.ALUNO,
            name="Aluno Sem Turma",
            email="semturma@aluno.com",
            turmas_count=0,
        )
        await self.member_repo.save(aluno_regular)
        await self.member_repo.save(aluno_sem_turma)

        # Filtro regular
        res_regular = await self.use_case.execute(
            ListStudentsInput(tenant_id=tenant.id, status="regular")
        )
        assert res_regular.total == 1
        assert res_regular.items[0].email == "regular@aluno.com"

        # Filtro sem_turma
        res_sem_turma = await self.use_case.execute(
            ListStudentsInput(tenant_id=tenant.id, status="sem_turma")
        )
        assert res_sem_turma.total == 1
        assert res_sem_turma.items[0].email == "semturma@aluno.com"

    async def test_list_students_sorting(self):
        tenant = Tenant(name="Universidade Teste", slug="univ-teste")
        await self.tenant_repo.save(tenant)

        aluno_a = TenantMember(
            tenant_id=tenant.id,
            user_id=uuid.uuid4(),
            role=UserRole.ALUNO,
            name="Ana Beatriz",
            email="ana@aluno.com",
            turmas_count=1,
        )
        aluno_z = TenantMember(
            tenant_id=tenant.id,
            user_id=uuid.uuid4(),
            role=UserRole.ALUNO,
            name="Zeca Pagodinho",
            email="zeca@aluno.com",
            turmas_count=5,
        )
        await self.member_repo.save(aluno_a)
        await self.member_repo.save(aluno_z)

        # Ordenar Nome DESC (Z -> A)
        res_desc = await self.use_case.execute(
            ListStudentsInput(tenant_id=tenant.id, sort_by="name", order="desc")
        )
        assert res_desc.items[0].name == "Zeca Pagodinho"
        assert res_desc.items[1].name == "Ana Beatriz"

        # Ordenar Turmas DESC (Mais turmas -> Menos turmas)
        res_turmas = await self.use_case.execute(
            ListStudentsInput(tenant_id=tenant.id, sort_by="turmas_count", order="desc")
        )
        assert res_turmas.items[0].name == "Zeca Pagodinho"
        assert res_turmas.items[1].name == "Ana Beatriz"
