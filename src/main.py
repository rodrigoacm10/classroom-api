from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from config.settings import settings
from modules.auth.interface.router import router as auth_router
from modules.tenant.interface.router import router as tenant_router
from modules.user.interface.router import router as user_router
from security.rate_limiter import limiter

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
)

# Configuração do Rate Limiter (Slowapi + Redis)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

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


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "API is running"}
