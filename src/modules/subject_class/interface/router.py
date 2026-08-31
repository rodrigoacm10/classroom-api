from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from infra.database.session import get_db
from modules.room.infra.repositories.room_sqlalchemy_repository import RoomSQLAlchemyRepository
from modules.subject_class.application.use_cases.create_subject_class import (
    CreateSubjectClassInput,
    CreateSubjectClassUseCase,
)
from modules.subject_class.application.use_cases.delete_subject_class import (
    DeleteSubjectClassInput,
    DeleteSubjectClassUseCase,
)
from modules.subject_class.application.use_cases.get_subject_class import (
    GetSubjectClassInput,
    GetSubjectClassUseCase,
)
from modules.subject_class.application.use_cases.list_subject_classes import (
    ListSubjectClassesInput,
    ListSubjectClassesUseCase,
)
from modules.subject_class.application.use_cases.update_subject_class import (
    UpdateSubjectClassInput,
    UpdateSubjectClassUseCase,
)
from modules.subject_class.infra.repositories.subject_class_sqlalchemy_repository import (
    SubjectClassSQLAlchemyRepository,
)
from modules.subject_class.interface.schemas.subject_class_schemas import (
    CreateSubjectClassRequest,
    SubjectClassResponse,
    UpdateSubjectClassRequest,
)
from modules.tenant.infra.repositories.tenant_member_sqlalchemy_repository import (
    TenantMemberSQLAlchemyRepository,
)
from modules.tenant.infra.repositories.tenant_sqlalchemy_repository import TenantSQLAlchemyRepository
from modules.user.domain.entities.user import User
from security.dependencies.current_user import get_current_user
from security.dependencies.require_role import require_role
from shared.enums.user_role import UserRole

router = APIRouter(prefix="/tenants/{tenant_id}/subject-classes", tags=["subject-classes"])


@router.post(
    "",
    response_model=SubjectClassResponse,
    status_code=201,
    dependencies=[Depends(require_role(UserRole.ADMIN, UserRole.PROFESSOR))],
)
async def create_subject_class(
    tenant_id: UUID,
    body: CreateSubjectClassRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SubjectClassResponse:
    """Cadastra uma nova turma de disciplina para a Tenant. Requer papel ADMIN ou PROFESSOR."""
    subject_class_repo = SubjectClassSQLAlchemyRepository(session=db)
    tenant_repo = TenantSQLAlchemyRepository(session=db)
    room_repo = RoomSQLAlchemyRepository(session=db)
    member_repo = TenantMemberSQLAlchemyRepository(session=db)
    use_case = CreateSubjectClassUseCase(
        subject_class_repo=subject_class_repo,
        tenant_repo=tenant_repo,
        room_repo=room_repo,
        member_repo=member_repo,
    )
    subject_class = await use_case.execute(
        CreateSubjectClassInput(
            tenant_id=tenant_id,
            professor_id=current_user.id,
            room_id=body.room_id,
            name=body.name,
            discipline_name=body.discipline_name,
        )
    )
    return SubjectClassResponse.model_validate(subject_class)


@router.get("", response_model=list[SubjectClassResponse])
async def list_subject_classes(
    tenant_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> list[SubjectClassResponse]:
    """Lista todas as turmas ativas (não deletadas) de uma Tenant."""
    subject_class_repo = SubjectClassSQLAlchemyRepository(session=db)
    tenant_repo = TenantSQLAlchemyRepository(session=db)
    use_case = ListSubjectClassesUseCase(subject_class_repo=subject_class_repo, tenant_repo=tenant_repo)

    classes = await use_case.execute(ListSubjectClassesInput(tenant_id=tenant_id))
    return [SubjectClassResponse.model_validate(c) for c in classes]


@router.get("/{subject_class_id}", response_model=SubjectClassResponse)
async def get_subject_class(
    tenant_id: UUID,
    subject_class_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> SubjectClassResponse:
    """Retorna os detalhes de uma turma. Retorna 404 se deletada ou inexistente."""
    subject_class_repo = SubjectClassSQLAlchemyRepository(session=db)
    use_case = GetSubjectClassUseCase(subject_class_repo=subject_class_repo)

    subject_class = await use_case.execute(
        GetSubjectClassInput(subject_class_id=subject_class_id, tenant_id=tenant_id)
    )
    return SubjectClassResponse.model_validate(subject_class)


@router.patch(
    "/{subject_class_id}",
    response_model=SubjectClassResponse,
    dependencies=[Depends(require_role(UserRole.ADMIN, UserRole.PROFESSOR))],
)
async def update_subject_class(
    tenant_id: UUID,
    subject_class_id: UUID,
    body: UpdateSubjectClassRequest,
    db: AsyncSession = Depends(get_db),
) -> SubjectClassResponse:
    """Atualiza parcialmente os dados de uma turma. Retorna 404 se deletada."""
    subject_class_repo = SubjectClassSQLAlchemyRepository(session=db)
    room_repo = RoomSQLAlchemyRepository(session=db)
    use_case = UpdateSubjectClassUseCase(subject_class_repo=subject_class_repo, room_repo=room_repo)

    subject_class = await use_case.execute(
        UpdateSubjectClassInput(
            subject_class_id=subject_class_id,
            tenant_id=tenant_id,
            name=body.name,
            discipline_name=body.discipline_name,
            room_id=body.room_id,
        )
    )
    return SubjectClassResponse.model_validate(subject_class)


@router.delete(
    "/{subject_class_id}",
    status_code=204,
    dependencies=[Depends(require_role(UserRole.ADMIN))],
)
async def delete_subject_class(
    tenant_id: UUID,
    subject_class_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Soft-delete de uma turma. Requer papel ADMIN. Retorna 404 se já deletada."""
    subject_class_repo = SubjectClassSQLAlchemyRepository(session=db)
    use_case = DeleteSubjectClassUseCase(subject_class_repo=subject_class_repo)

    await use_case.execute(
        DeleteSubjectClassInput(subject_class_id=subject_class_id, tenant_id=tenant_id)
    )
