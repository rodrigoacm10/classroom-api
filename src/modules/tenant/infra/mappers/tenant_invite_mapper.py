from uuid import UUID

from infra.database.models.tenant_invite import TenantInviteModel
from modules.tenant.domain.entities.tenant_invite import TenantInvite


class TenantInviteMapper:
    @staticmethod
    def to_domain(model: TenantInviteModel) -> TenantInvite:
        raw_classes = model.subject_class_ids or []
        subject_class_ids = [UUID(str(cid)) for cid in raw_classes]
        return TenantInvite(
            id=model.id,
            tenant_id=model.tenant_id,
            invited_by=model.invited_by,
            email=model.email,
            role=model.role,
            token=model.token,
            expires_at=model.expires_at,
            accepted_at=model.accepted_at,
            revoked_at=model.revoked_at,
            subject_class_ids=subject_class_ids,
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
            revoked_at=entity.revoked_at,
            subject_class_ids=[str(cid) for cid in entity.subject_class_ids]
            if entity.subject_class_ids
            else None,
        )
