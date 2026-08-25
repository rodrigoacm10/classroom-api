from fastapi import FastAPI

from config.settings import settings
from modules.auth.interface.router import router as auth_router
from modules.tenant.interface.router import router as tenant_router
from modules.user.interface.router import router as user_router
from shared.exception_handlers import register_exception_handlers

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
)

register_exception_handlers(app)

app.include_router(auth_router)
app.include_router(user_router)
app.include_router(tenant_router)


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "API is running"}
