from dataclasses import dataclass
from uuid import UUID

from modules.room.domain.repositories.room_repository import RoomRepository
from modules.subject_class.domain.entities.subject_class import SubjectClass
from modules.subject_class.domain.repositories.subject_class_repository import SubjectClassRepository
from modules.tenant.domain.repositories.tenant_repository import TenantMemberRepository, TenantRepository
from shared.enums.user_role import UserRole
from shared.exceptions import BusinessRuleException, ResourceNotFoundException


@dataclass
class CreateSubjectClassInput:
    tenant_id: UUID
    professor_id: UUID  # user_id do professor/criador
    room_id: UUID
    name: str
    discipline_name: str


class CreateSubjectClassUseCase:

    def __init__(
        self,
        subject_class_repo: SubjectClassRepository,
        tenant_repo: TenantRepository,
        room_repo: RoomRepository,
        member_repo: TenantMemberRepository,
    ) -> None:
        self.subject_class_repo = subject_class_repo
        self.tenant_repo = tenant_repo
        self.room_repo = room_repo
        self.member_repo = member_repo

    async def execute(self, data: CreateSubjectClassInput) -> SubjectClass:
        tenant = await self.tenant_repo.find_by_id(data.tenant_id)
        if not tenant or tenant.deleted:
            raise ResourceNotFoundException("Instituição/tenant não encontrada.")

        room = await self.room_repo.find_by_id_and_tenant(
            room_id=data.room_id,
            tenant_id=data.tenant_id,
        )
        if not room:
            raise ResourceNotFoundException("Sala não encontrada.")

        professor_member = await self.member_repo.find_by_tenant_and_user(
            tenant_id=data.tenant_id,
            user_id=data.professor_id,
        )
        if not professor_member or professor_member.deleted:
            raise ResourceNotFoundException("Professor não encontrado nesta instituição.")

        if professor_member.role == UserRole.ALUNO:
            raise BusinessRuleException("Apenas professores ou administradores podem ministrar turmas.")

        subject_class = SubjectClass(
            tenant_id=data.tenant_id,
            professor_id=professor_member.id,  # Armazena o ID do TenantMember!
            room_id=data.room_id,
            name=data.name,
            discipline_name=data.discipline_name,
        )
        return await self.subject_class_repo.save(subject_class)
