from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_name: str = "Classroom API"
    app_version: str = "0.1.0"
    database_url: str = "postgresql+psycopg://classroom:classroom@localhost:5432/classroom"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "change-me"


settings = Settings()
