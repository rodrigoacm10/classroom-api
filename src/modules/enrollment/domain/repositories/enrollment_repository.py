from typing import Protocol
from uuid import UUID

from modules.enrollment.domain.entities.enrollment import Enrollment
from shared.enums.enrollment_status import EnrollmentStatus


class EnrollmentRepository(Protocol):

    async def save(self, enrollment: Enrollment) -> Enrollment: ...

    async def find_by_id(
        self, enrollment_id: UUID, include_deleted: bool = False
    ) -> Enrollment | None: ...

    async def find_by_class_and_member(
        self,
        subject_class_id: UUID,
        tenant_member_id: UUID,
        include_deleted: bool = False,
    ) -> Enrollment | None: ...

    async def list_by_subject_class(
        self,
        subject_class_id: UUID,
        status: EnrollmentStatus | None = None,
        include_deleted: bool = False,
    ) -> list[Enrollment]: ...

    async def list_by_member(
        self,
        tenant_member_id: UUID,
        status: EnrollmentStatus | None = None,
        include_deleted: bool = False,
    ) -> list[Enrollment]: ...

    async def drop_all_active_for_member(self, tenant_member_id: UUID) -> int:
        """Altera o status de todas as matrículas ativas (e não deletadas) de um tenant_member para DROPPED.
        Retorna o número de matrículas afetadas.
        Chamado pelo UpdateTenantMemberRoleUseCase quando a role muda de ALUNO.
        """
        ...
