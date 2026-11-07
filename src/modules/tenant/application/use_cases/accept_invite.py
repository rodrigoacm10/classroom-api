from datetime import datetime, timezone

from modules.enrollment.domain.entities.enrollment import Enrollment
from modules.enrollment.domain.repositories.enrollment_repository import EnrollmentRepository
from modules.tenant.domain.entities.tenant_member import TenantMember
from modules.tenant.domain.repositories.tenant_invite_repository import TenantInviteRepository
from modules.tenant.domain.repositories.tenant_repository import TenantMemberRepository
from modules.user.domain.entities.user import User
from shared.enums.enrollment_status import EnrollmentStatus
from shared.enums.user_role import UserRole
from shared.exceptions import (
    BusinessRuleException,
    ForbiddenException,
    ResourceNotFoundException,
)


class AcceptInviteUseCase:
    def __init__(
        self,
        invite_repo: TenantInviteRepository,
        member_repo: TenantMemberRepository,
        enrollment_repo: EnrollmentRepository | None = None,
    ) -> None:
        self.invite_repo = invite_repo
        self.member_repo = member_repo
        self.enrollment_repo = enrollment_repo

    async def execute(self, token: str, user: User) -> TenantMember:
        # 1. Busca o convite
        invite = await self.invite_repo.find_by_token(token)
        if not invite:
            raise ResourceNotFoundException("Convite não encontrado.")

        # 2. Valida status
        if invite.is_accepted:
            raise BusinessRuleException("Este convite já foi aceito.")

        if invite.is_revoked:
            raise BusinessRuleException("Este convite foi revogado pelo administrador.")

        if invite.is_expired:
            raise BusinessRuleException("Este convite está expirado.")

        # 3. Valida se o e-mail do usuário autenticado é o mesmo do convite
        if user.email.lower() != invite.email.lower():
            raise ForbiddenException("Este convite foi enviado para outro endereço de e-mail.")

        # 4. Verifica se já é membro (idempotência/race condition)
        existing_member = await self.member_repo.find_by_tenant_and_user(
            tenant_id=invite.tenant_id,
            user_id=user.id,
        )
        if existing_member:
            invite.accepted_at = datetime.now(timezone.utc)
            await self.invite_repo.save(invite)
            target_member = existing_member
        else:
            # 5. Vincula o usuário como membro do tenant
            member = TenantMember(
                tenant_id=invite.tenant_id,
                user_id=user.id,
                role=invite.role,
            )
            target_member = await self.member_repo.save(member)

        # 6. Auto-matrícula nas turmas vinculadas ao convite (caso aluno)
        if self.enrollment_repo and invite.role == UserRole.ALUNO and invite.subject_class_ids:
            for class_id in invite.subject_class_ids:
                try:
                    existing_enrollment = await self.enrollment_repo.find_by_class_and_member(
                        subject_class_id=class_id,
                        tenant_member_id=target_member.id,
                        include_deleted=False,
                    )
                    if not existing_enrollment:
                        new_enrollment = Enrollment(
                            subject_class_id=class_id,
                            tenant_member_id=target_member.id,
                            status=EnrollmentStatus.ACTIVE,
                        )
                        await self.enrollment_repo.save(new_enrollment)
                    elif existing_enrollment.status != EnrollmentStatus.ACTIVE:
                        existing_enrollment.status = EnrollmentStatus.ACTIVE
                        existing_enrollment.dropped_at = None
                        existing_enrollment.drop_reason = None
                        await self.enrollment_repo.save(existing_enrollment)
                except Exception:
                    # Se alguma turma falhar (ex: deletada), não interrompe a ativação do membro
                    pass

        # 7. Marca o convite como aceito
        invite.accepted_at = datetime.now(timezone.utc)
        await self.invite_repo.save(invite)

        return target_member
