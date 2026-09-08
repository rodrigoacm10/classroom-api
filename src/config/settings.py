from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_name: str = "Classroom API"
    app_version: str = "0.1.0"
    database_url: str = "postgresql+psycopg://classroom:classroom@localhost:5432/classroom"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "change-me-super-secret-key-that-is-at-least-32-bytes-long"
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:5173", "http://localhost:8000"]
    access_token_expire_minutes: int = 30       # 30 minutos para o Access Token
    refresh_token_expire_days: int = 7          # 7 dias para o Refresh Token
    cookie_secure: bool = False                 # True em produção (HTTPS apenas)
    cookie_samesite: Literal["lax", "none", "strict"] = "lax"                # "strict" em produção, "lax" em desenvolvimento
    resend_api_key: str = ""                    # Chave de API do Resend (ex: re_123456789)
    email_from: str = "onboarding@resend.dev"   # Remetente oficial de testes do Resend (ou seu domínio verificado)
    frontend_url: str = "http://localhost:3000" # URL base do frontend para montar links de aceite
    invite_expire_hours: int = 72               # Tempo de expiração do convite em horas
    password_reset_expire_minutes: int = 15     # Tempo de expiração do código de recuperação em minutos


settings = Settings()
