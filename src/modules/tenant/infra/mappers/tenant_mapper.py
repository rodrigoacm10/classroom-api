from infra.database.models.tenant import TenantModel
from modules.tenant.domain.entities.tenant import Tenant


class TenantMapper:

    @staticmethod
    def to_domain(model: TenantModel) -> Tenant:
        return Tenant(
            id=model.id,
            name=model.name,
            slug=model.slug,
            created_at=model.created_at,
        )

    @staticmethod
    def to_model(entity: Tenant) -> TenantModel:
        return TenantModel(
            id=entity.id,
            name=entity.name,
            slug=entity.slug,
        )
