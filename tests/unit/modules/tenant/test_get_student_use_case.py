import uuid

import pytest

from modules.tenant.application.use_cases.get_student import (
    GetStudentInput,
    GetStudentUseCase,
)
from modules.tenant.domain.entities.tenant import Tenant
from modules.tenant.domain.entities.tenant_member import TenantMember
from shared.enums.user_role import UserRole
from shared.exceptions import ResourceNotFoundException
from tests.unit.fakes.fake_tenant_member_repository import FakeTenantMemberRepository
from tests.unit.fakes.fake_tenant_repository import FakeTenantRepository


@pytest.mark.asyncio
class TestGetStudentUseCase:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.tenant_repo = FakeTenantRepository()
        self.member_repo = FakeTenantMemberRepository()
        self.use_case = GetStudentUseCase(
            tenant_repo=self.tenant_repo,
            member_repo=self.member_repo,
        )

    async def test_get_student_success(self):
        tenant = Tenant(name="Universidade Teste", slug="univ-teste")
        await self.tenant_repo.save(tenant)

        aluno = TenantMember(
            tenant_id=tenant.id,
            user_id=uuid.uuid4(),
            role=UserRole.ALUNO,
            name="Lucas Oliveira",
            email="lucas@aluno.com",
        )
        await self.member_repo.save(aluno)

        result = await self.use_case.execute(
            GetStudentInput(tenant_id=tenant.id, student_id=aluno.id)
        )

        assert result.id == aluno.id
        assert result.name == "Lucas Oliveira"
        assert result.email == "lucas@aluno.com"
        assert result.role == UserRole.ALUNO

    async def test_get_student_not_found_raises_exception(self):
        tenant = Tenant(name="Universidade Teste", slug="univ-teste")
        await self.tenant_repo.save(tenant)

        with pytest.raises(ResourceNotFoundException, match="Aluno não encontrado"):
            await self.use_case.execute(
                GetStudentInput(tenant_id=tenant.id, student_id=uuid.uuid4())
            )

    async def test_get_student_non_existent_tenant_raises_exception(self):
        with pytest.raises(ResourceNotFoundException, match="Instituição não encontrada"):
            await self.use_case.execute(
                GetStudentInput(tenant_id=uuid.uuid4(), student_id=uuid.uuid4())
            )
