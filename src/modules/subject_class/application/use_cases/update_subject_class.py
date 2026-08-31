from dataclasses import dataclass
from uuid import UUID

from modules.room.domain.repositories.room_repository import RoomRepository
from modules.subject_class.domain.entities.subject_class import SubjectClass
from modules.subject_class.domain.repositories.subject_class_repository import SubjectClassRepository
from shared.exceptions import ResourceNotFoundException


@dataclass
class UpdateSubjectClassInput:
    subject_class_id: UUID
    tenant_id: UUID
    name: str | None = None
    discipline_name: str | None = None
    room_id: UUID | None = None


class UpdateSubjectClassUseCase:

    def __init__(
        self,
        subject_class_repo: SubjectClassRepository,
        room_repo: RoomRepository,
    ) -> None:
        self.subject_class_repo = subject_class_repo
        self.room_repo = room_repo

    async def execute(self, data: UpdateSubjectClassInput) -> SubjectClass:
        subject_class = await self.subject_class_repo.find_by_id_and_tenant(
            subject_class_id=data.subject_class_id,
            tenant_id=data.tenant_id,
        )
        if not subject_class:
            raise ResourceNotFoundException("Turma não encontrada.")

        if data.room_id is not None:
            room = await self.room_repo.find_by_id_and_tenant(
                room_id=data.room_id,
                tenant_id=data.tenant_id,
            )
            if not room:
                raise ResourceNotFoundException("Sala não encontrada.")
            subject_class.room_id = data.room_id

        if data.name is not None:
            subject_class.name = data.name
        if data.discipline_name is not None:
            subject_class.discipline_name = data.discipline_name

        return await self.subject_class_repo.save(subject_class)
