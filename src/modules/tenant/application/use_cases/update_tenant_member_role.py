from dataclasses import dataclass
from uuid import UUID

from modules.enrollment.domain.repositories.enrollment_repository import EnrollmentRepository
from modules.tenant.domain.entities.tenant_member import TenantMember
from modules.tenant.domain.repositories.tenant_repository import (
    TenantMemberRepository,
    TenantRepository,
)
from shared.enums.user_role import UserRole
from shared.exceptions import BusinessRuleException, ResourceNotFoundException


@dataclass
class UpdateTenantMemberRoleInput:
    tenant_id: UUID
    user_id_to_update: UUID
    new_role: UserRole


class UpdateTenantMemberRoleUseCase:

    def __init__(
        self,
        tenant_repo: TenantRepository,
        member_repo: TenantMemberRepository,
        enrollment_repo: EnrollmentRepository | None = None,
    ) -> None:
        self.tenant_repo = tenant_repo
        self.member_repo = member_repo
        self.enrollment_repo = enrollment_repo

    async def execute(self, data: UpdateTenantMemberRoleInput) -> TenantMember:
        # 1. Verificar se a tenant existe e não está deletada
        tenant = await self.tenant_repo.find_by_id(data.tenant_id)
        if not tenant or tenant.deleted:
            raise ResourceNotFoundException("Instituição/tenant não encontrada.")

        # 2. Buscar o membro ativo a ter sua role alterada
        member = await self.member_repo.find_by_tenant_and_user(
            tenant_id=data.tenant_id,
            user_id=data.user_id_to_update,
            include_deleted=False,
        )
        if not member:
            raise ResourceNotFoundException("Membro não encontrado nesta instituição.")

        # 3. Se a role não está mudando, nada a fazer
        if member.role == data.new_role:
            return member

        # 4. Trava de segurança: se o membro é atualmente ADMIN e está sendo alterado para outra role,
        # verificar se não estamos rebaixando o único administrador da instituição.
        if member.role == UserRole.ADMIN and data.new_role != UserRole.ADMIN:
            active_admins = await self.member_repo.count_active_admins(data.tenant_id)
            if active_admins <= 1:
                raise BusinessRuleException(
                    "Não é possível alterar a função do único administrador da instituição."
                )

        old_role = member.role

        # 5. Atualiza a role e persiste
        member.role = data.new_role
        updated_member = await self.member_repo.save(member)

        # 6. Se a role anterior era ALUNO e a nova não é ALUNO,
        # cancela todas as matrículas ativas desse membro
        if old_role == UserRole.ALUNO and data.new_role != UserRole.ALUNO:
            if self.enrollment_repo:
                await self.enrollment_repo.drop_all_active_for_member(tenant_member_id=member.id)

        return updated_member
