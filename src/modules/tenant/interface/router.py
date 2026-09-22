from modules.tenant.interface.invite_router import invites_router, tenant_invites_router
from modules.tenant.interface.tenant_router import router as tenant_router

# Manter alias retrocompatível para `router`
router = tenant_router

__all__ = ["router", "tenant_router", "invites_router", "tenant_invites_router"]
