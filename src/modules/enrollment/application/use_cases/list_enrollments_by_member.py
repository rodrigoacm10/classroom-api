from dataclasses import dataclass
from uuid import UUID

from modules.enrollment.domain.entities.enrollment import Enrollment
from modules.enrollment.domain.repositories.enrollment_repository import EnrollmentRepository
from modules.tenant.domain.repositories.tenant_repository import TenantMemberRepository
from shared.enums.enrollment_status import EnrollmentStatus
from shared.exceptions import BusinessRuleException, ResourceNotFoundException


@dataclass
class ListEnrollmentsByMemberInput:
    tenant_id: UUID
    tenant_member_id: UUID
    status: EnrollmentStatus | None = None
    include_deleted: bool = False


class ListEnrollmentsByMemberUseCase:

    def __init__(
        self,
        enrollment_repo: EnrollmentRepository,
        member_repo: TenantMemberRepository,
    ) -> None:
        self.enrollment_repo = enrollment_repo
        self.member_repo = member_repo

    async def execute(self, data: ListEnrollmentsByMemberInput) -> list[Enrollment]:
        member = await self.member_repo.find_by_id(data.tenant_member_id, include_deleted=False)
        if not member:
            raise ResourceNotFoundException("Membro não encontrado.")

        if member.tenant_id != data.tenant_id:
            raise BusinessRuleException("O membro não pertence a esta instituição.")

        return await self.enrollment_repo.list_by_member(
            tenant_member_id=data.tenant_member_id,
            status=data.status,
            include_deleted=data.include_deleted,
        )
