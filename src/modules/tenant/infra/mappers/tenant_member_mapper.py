from infra.database.models.tenant import TenantMemberModel
from modules.tenant.domain.entities.tenant_member import TenantMember


class TenantMemberMapper:
    @staticmethod
    def to_domain(
        model: TenantMemberModel,
        user_name: str | None = None,
        user_email: str | None = None,
    ) -> TenantMember:
        return TenantMember(
            id=model.id,
            tenant_id=model.tenant_id,
            user_id=model.user_id,
            role=model.role,
            deleted=model.deleted,
            name=user_name or "",
            email=user_email or "",
            created_at=model.created_at,
        )

    @staticmethod
    def to_model(entity: TenantMember) -> TenantMemberModel:
        return TenantMemberModel(
            id=entity.id,
            tenant_id=entity.tenant_id,
            user_id=entity.user_id,
            role=entity.role,
            deleted=entity.deleted,
        )
