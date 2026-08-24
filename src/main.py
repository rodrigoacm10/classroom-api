from fastapi import FastAPI

from config.settings import settings
from modules.auth.interface.router import router as auth_router
from modules.user.interface.router import router as user_router

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
)

app.include_router(auth_router)
app.include_router(user_router)


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "API is running"}
