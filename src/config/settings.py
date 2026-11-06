from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Classroom API"
    app_version: str = "0.2.0"
    database_url: str = "postgresql+psycopg://classroom:classroom@localhost:5432/classroom"
    database_pool_size: int = 20  # Conexões ativas permanentes mantidas no pool
    database_max_overflow: int = 20  # Conexões adicionais permitidas durante picos (total: 40)
    database_pool_timeout: int = (
        15  # Segundos de espera máxima por conexão livre antes de TimeoutError
    )
    database_pool_pre_ping: bool = True  # Validação de liveness antes de reusar conexão do pool
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "change-me-super-secret-key-that-is-at-least-32-bytes-long"
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:8000",
    ]
    access_token_expire_minutes: int = 15  # Reduzido para 15 min (minimiza a janela de exposição)
    refresh_token_expire_days: int = 7  # 7 dias para o Refresh Token
    cookie_secure: bool = False  # True em produção (HTTPS apenas)
    cookie_samesite: Literal["lax", "none", "strict"] = (
        "lax"  # "strict" em produção, "lax" em desenvolvimento
    )

    @property
    def refresh_cookie_name(self) -> str:
        """
        RFC 6265bis: Em produção segura (HTTPS), utiliza o prefixo restritivo '__Host-'.
        Isso bloqueia sobrescritas por subdomínios e força o motor do navegador a exigir Secure=True.
        Em ambiente de desenvolvimento sem SSL, utiliza 'refresh_token'.
        """
        return "__Host-refresh_token" if self.cookie_secure else "refresh_token"

    # E-mail / Provedor Resend
    resend_api_key: str = ""  # Chave de API do Resend (ex: re_123456789)
    mail_domain: str = "rodrigoacm.com"  # Domínio padrão para envio de e-mails
    mail_from_prefix: str = "noreply"  # Prefixo do e-mail (ex: noreply -> noreply@rodrigoacm.com)
    mail_from_name: str = "Classroom"  # Nome de exibição do remetente nos clientes de e-mail
    email_from: str = (
        ""  # Sobrescreve a composição automática caso fornecido explicitamente no .env
    )

    @model_validator(mode="after")
    def _assemble_email_from(self) -> "Settings":
        """
        Monta o remetente oficial de e-mail de forma dinâmica e desacoplada:
        1. Se `email_from` estiver preenchido expressamente no .env, utiliza-o diretamente.
        2. Se houver `mail_domain`, monta no padrão RFC: "Nome <prefixo@dominio>".
        3. Caso contrário, faz fallback seguro para 'onboarding@resend.dev' para testes locais.
        """
        if not self.email_from or not self.email_from.strip():
            domain = self.mail_domain.strip() if self.mail_domain else ""
            prefix = self.mail_from_prefix.strip() if self.mail_from_prefix else "noreply"
            name = self.mail_from_name.strip() if self.mail_from_name else self.app_name

            if domain:
                address = f"{prefix}@{domain}"
                self.email_from = f"{name} <{address}>" if name else address
            else:
                self.email_from = "onboarding@resend.dev"
        return self

    @property
    def mail_from_address(self) -> str:
        """Retorna apenas o endereço puro de e-mail (ex: noreply@rodrigoacm.com)."""
        domain = self.mail_domain.strip() if self.mail_domain else ""
        prefix = self.mail_from_prefix.strip() if self.mail_from_prefix else "noreply"
        return f"{prefix}@{domain}" if domain else "onboarding@resend.dev"

    frontend_url: str = "http://localhost:3000"  # URL base do frontend para montar links de aceite
    invite_expire_hours: int = 72  # Tempo de expiração do convite em horas
    password_reset_expire_minutes: int = (
        15  # Tempo de expiração do código de recuperação em minutos
    )
    password_reset_token_expire_minutes: int = (
        10  # Tempo de expiração do token de redefinição (etapa 2 -> 3) em minutos
    )

    # Firebase Cloud Messaging
    firebase_credentials_path: str = "credentials/firebase-service-account.json"
    firebase_credentials_json: str = ""  # Conteúdo JSON inline (para produção / CI-CD)

    # Celery
    celery_broker_url: str = ""  # Se vazio, utiliza redis_url como fallback
    celery_result_backend: str = ""  # Se vazio, utiliza redis_url como fallback

    # Cloudflare R2 — Object Storage (evidências fotográficas)
    cloudflare_r2_account_id: str = ""
    cloudflare_r2_access_key_id: str = ""
    cloudflare_r2_secret_access_key: str = ""
    cloudflare_r2_bucket_name: str = "classroom-evidence"
    cloudflare_r2_public_url: str = ""          # Ex: https://pub-XXXX.r2.dev

    # Limpeza de uploads de evidência: tempo máximo que uma foto pode ficar `pending`
    # (enviada, mas sem confirmação de presença) antes de ser apagada do storage.
    evidence_upload_ttl_minutes: int = 120

    # Módulo de relatórios — estratégia de paralelismo
    report_strategy: str = "process_pool"  # "sequential" | "process_pool" | "thread_pool_numpy"
    report_max_workers: int = 0  # 0 = usar cpu_budget() automaticamente

    @property
    def effective_celery_broker(self) -> str:
        return self.celery_broker_url or self.redis_url

    @property
    def effective_celery_backend(self) -> str:
        return self.celery_result_backend or self.redis_url

    @property
    def r2_endpoint_url(self) -> str:
        return f"https://{self.cloudflare_r2_account_id}.r2.cloudflarestorage.com"


settings = Settings()
