from infra.database.models.tenant_invite import TenantInviteModel
from modules.tenant.domain.entities.tenant_invite import TenantInvite


class TenantInviteMapper:

    @staticmethod
    def to_domain(model: TenantInviteModel) -> TenantInvite:
        return TenantInvite(
            id=model.id,
            tenant_id=model.tenant_id,
            invited_by=model.invited_by,
            email=model.email,
            role=model.role,
            token=model.token,
            expires_at=model.expires_at,
            accepted_at=model.accepted_at,
            created_at=model.created_at,
        )

    @staticmethod
    def to_model(entity: TenantInvite) -> TenantInviteModel:
        return TenantInviteModel(
            id=entity.id,
            tenant_id=entity.tenant_id,
            invited_by=entity.invited_by,
            email=entity.email,
            role=entity.role,
            token=entity.token,
            expires_at=entity.expires_at,
            accepted_at=entity.accepted_at,
        )
