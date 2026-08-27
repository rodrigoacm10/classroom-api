import uuid
from uuid import UUID

from modules.tenant.domain.entities.tenant import Tenant
from shared.enums.user_role import UserRole


class TenantFactory:
    """Factory para criar entidades Tenant e TenantMember para testes."""

    @staticmethod
    def make(**overrides) -> Tenant:
        """Cria uma entidade Tenant em memória com valores padrão."""
        defaults: dict = {
            "id": uuid.uuid4(),
            "name": "Escola Exemplo",
            "slug": f"escola-{uuid.uuid4().hex[:6]}",
            "active": True,
            "deleted": False,
        }
        merged = {**defaults, **overrides}
        if isinstance(merged["id"], str):
            merged["id"] = UUID(merged["id"])
        return Tenant(**merged)

    @staticmethod
    async def create(session, **overrides):
        """
        Cria e persiste um TenantModel no banco de dados de teste.
        Use apenas em testes de integração e E2E.

        O slug é único por padrão (via sufixo UUID) para evitar colisões de
        constraint UNIQUE quando vários testes rodam na mesma sessão de DB.
        """
        from infra.database.models.tenant import TenantModel

        defaults: dict = {
            "id": uuid.uuid4(),
            "name": "Escola Exemplo",
            "slug": f"escola-{uuid.uuid4().hex[:6]}",
            "active": True,
            "deleted": False,
        }
        data = {**defaults, **overrides}
        if isinstance(data["id"], str):
            data["id"] = UUID(data["id"])

        model = TenantModel(**data)
        session.add(model)
        await session.flush()
        await session.refresh(model)
        return model

    @staticmethod
    async def create_member(session, tenant_id: UUID, user_id: UUID, **overrides):
        """
        Cria e persiste um TenantMemberModel vinculando um usuário a uma tenant.

        Requer que tanto o Tenant quanto o User já existam no banco
        (foreign key constraints).

        Uso:
            tenant = await TenantFactory.create(session)
            user   = await UserFactory.create(session)
            member = await TenantFactory.create_member(
                session,
                tenant_id=tenant.id,
                user_id=user.id,
            )
        """
        from infra.database.models.tenant import TenantMemberModel

        defaults: dict = {
            "id": uuid.uuid4(),
            "tenant_id": tenant_id,
            "user_id": user_id,
            "role": UserRole.PROFESSOR,
        }
        data = {**defaults, **overrides}

        model = TenantMemberModel(**data)
        session.add(model)
        await session.flush()
        await session.refresh(model)
        return model
