from pydantic import BaseModel, EmailStr, Field


class ForgotPasswordRequest(BaseModel):
    """Payload para solicitação de código de recuperação de senha."""

    email: EmailStr


class VerifyResetCodeRequest(BaseModel):
    """Payload para validação do código de recuperação de senha (Etapa 2)."""

    email: EmailStr
    code: str = Field(
        ...,
        min_length=6,
        max_length=6,
        pattern=r"^\d{6}$",
        description="Código numérico de 6 dígitos recebido por e-mail",
    )


class VerifyResetCodeResponse(BaseModel):
    """Resposta com reset_token temporário após validação do código OTP."""

    reset_token: str = Field(
        ...,
        description="Token JWT temporário para autorizar a redefinição de senha",
    )
    token_type: str = Field(
        "Bearer",
        description="Tipo de token",
    )
    expires_in: int = Field(
        ...,
        description="Tempo de expiração do reset_token em segundos",
    )


class ResetPasswordRequest(BaseModel):
    """Payload para redefinição de senha utilizando o reset_token temporário (Etapa 3)."""

    reset_token: str = Field(
        ...,
        min_length=1,
        description="Token temporário obtido na etapa de verificação de código",
    )
    new_password: str = Field(
        ...,
        min_length=6,
        description="Nova senha do usuário (mínimo de 6 caracteres)",
    )
