from dataclasses import dataclass
from uuid import UUID

from modules.subject_class.domain.entities.subject_class_metrics import SubjectClassMetrics
from modules.subject_class.domain.repositories.subject_class_repository import (
    SubjectClassRepository,
)
from modules.tenant.domain.repositories.tenant_repository import (
    TenantMemberRepository,
    TenantRepository,
)
from shared.enums.user_role import UserRole
from shared.exceptions import ForbiddenException, ResourceNotFoundException


@dataclass
class GetSubjectClassMetricsInput:
    tenant_id: UUID
    user_id: UUID
    user_role: UserRole | None = None
    professor_id: UUID | None = None
    days: int | None = 30


class GetSubjectClassMetricsUseCase:
    def __init__(
        self,
        subject_class_repo: SubjectClassRepository,
        tenant_repo: TenantRepository,
        member_repo: TenantMemberRepository,
    ) -> None:
        self.subject_class_repo = subject_class_repo
        self.tenant_repo = tenant_repo
        self.member_repo = member_repo

    async def execute(self, data: GetSubjectClassMetricsInput) -> SubjectClassMetrics:
        tenant = await self.tenant_repo.find_by_id(data.tenant_id)
        if not tenant or tenant.deleted:
            raise ResourceNotFoundException("Instituição/tenant não encontrada.")

        if data.user_role not in (UserRole.ADMIN, UserRole.COORDENADOR, UserRole.PROFESSOR):
            raise ForbiddenException(
                "Apenas administradores, coordenadores e professores podem consultar métricas de turmas."
            )

        scoped_professor_id = data.professor_id
        if data.user_role == UserRole.PROFESSOR:
            # Professor só pode visualizar métricas das turmas das quais é responsável
            member = await self.member_repo.find_by_tenant_and_user(
                tenant_id=data.tenant_id,
                user_id=data.user_id,
            )
            if not member or member.deleted:
                raise ResourceNotFoundException("Vínculo do professor não encontrado nesta instituição.")
            scoped_professor_id = member.id

        return await self.subject_class_repo.get_metrics_by_tenant(
            tenant_id=data.tenant_id,
            professor_id=scoped_professor_id,
            days=data.days,
        )
