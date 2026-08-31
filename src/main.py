from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from config.settings import settings
from modules.auth.interface.router import router as auth_router
from modules.enrollment.interface.router import router as enrollment_router
from modules.room.interface.router import router as room_router
from modules.subject_class.interface.router import router as subject_class_router
from modules.tenant.interface.invite_router import invites_router, tenant_invites_router
from modules.tenant.interface.tenant_router import router as tenant_router
from modules.user.interface.router import router as user_router
from security.rate_limiter import limiter
from shared.exception_handlers import register_exception_handlers

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
)

# Registrar handlers globais de exceções de domínio (404, 403, 400, 409)
register_exception_handlers(app)

# Configuração do Rate Limiter (Slowapi + Redis)
app.state.limiter = limiter


async def rate_limit_handler(request: Request, exc: Exception) -> Response:
    if isinstance(exc, RateLimitExceeded):
        return _rate_limit_exceeded_handler(request, exc)
    return Response(status_code=429)


app.add_exception_handler(RateLimitExceeded, rate_limit_handler)

# Configuração do CORS (Cross-Origin Resource Sharing)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(user_router)
app.include_router(tenant_router)
app.include_router(room_router)
app.include_router(subject_class_router)
app.include_router(enrollment_router)
app.include_router(tenant_invites_router)
app.include_router(invites_router)



@app.get("/")
def root() -> dict[str, str]:
    return {"message": "API is running"}
