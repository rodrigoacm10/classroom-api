from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from infra.database.session import get_db
from modules.user.application.use_cases.create_user import CreateUserInput, CreateUserUseCase
from modules.user.infra.repositories.user_sqlalchemy_repository import UserSQLAlchemyRepository
from modules.user.interface.schemas.user_schemas import CreateUserRequest, UserResponse

router = APIRouter(prefix="/users", tags=["Users"])


@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: CreateUserRequest,
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    repository = UserSQLAlchemyRepository(session=db)
    use_case = CreateUserUseCase(repository=repository)

    try:
        user = await use_case.execute(
            CreateUserInput(name=body.name, email=body.email, password=body.password)
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))

    return UserResponse(
        id=user.id,
        name=user.name,
        email=user.email,
        created_at=user.created_at,
    )
