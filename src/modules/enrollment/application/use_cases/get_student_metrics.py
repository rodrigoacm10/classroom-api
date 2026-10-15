from dataclasses import dataclass
from uuid import UUID

from modules.enrollment.domain.entities.student_metrics import StudentMetrics
from modules.enrollment.domain.repositories.enrollment_repository import EnrollmentRepository
from modules.tenant.domain.repositories.tenant_repository import TenantMemberRepository
from shared.enums.enrollment_status import EnrollmentStatus
from shared.exceptions import (
    BusinessRuleException,
    ForbiddenException,
    ResourceNotFoundException,
)

RISK_THRESHOLD = 0.75


@dataclass
class GetStudentMetricsInput:
    tenant_id: UUID
    tenant_member_id: UUID | None = None
    user_id: UUID | None = None


class GetStudentMetricsUseCase:
    """Consolida os indicadores de frequência e turmas do aluno no tenant ativo."""

    def __init__(
        self,
        enrollment_repo: EnrollmentRepository,
        member_repo: TenantMemberRepository,
    ) -> None:
        self.enrollment_repo = enrollment_repo
        self.member_repo = member_repo

    async def execute(self, data: GetStudentMetricsInput) -> StudentMetrics:
        if data.user_id is not None:
            member = await self.member_repo.find_by_tenant_and_user(
                tenant_id=data.tenant_id,
                user_id=data.user_id,
                include_deleted=False,
            )
            if not member or getattr(member, "deleted", False):
                raise ForbiddenException("Aluno não encontrado nesta instituição.")
            resolved_member_id = member.id
        elif data.tenant_member_id is not None:
            member = await self.member_repo.find_by_id(data.tenant_member_id, include_deleted=False)
            if not member:
                raise ResourceNotFoundException("Membro não encontrado.")

            if member.tenant_id != data.tenant_id:
                raise BusinessRuleException("O membro não pertence a esta instituição.")
            resolved_member_id = data.tenant_member_id
        else:
            raise BusinessRuleException("É necessário informar tenant_member_id ou user_id.")

        summaries = await self.enrollment_repo.list_summaries_by_member(
            tenant_id=data.tenant_id,
            tenant_member_id=resolved_member_id,
            status=EnrollmentStatus.ACTIVE,
            include_deleted=False,
        )

        total_classes = len(summaries)
        classes_with_sessions = [s for s in summaries if s.total_sessions > 0]

        if classes_with_sessions:
            avg_rate = round(
                sum(s.attendance_rate for s in classes_with_sessions) / len(classes_with_sessions),
                4,
            )
            at_risk_count = sum(
                1 for s in classes_with_sessions if s.attendance_rate < RISK_THRESHOLD
            )
        else:
            avg_rate = 1.0
            at_risk_count = 0

        return StudentMetrics(
            total_classes=total_classes,
            average_attendance_rate=avg_rate,
            at_risk_count=at_risk_count,
        )
