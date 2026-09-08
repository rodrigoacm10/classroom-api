from pydantic import BaseModel, EmailStr, Field


class ForgotPasswordRequest(BaseModel):
    """Payload para solicitação de código de recuperação de senha."""
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    """Payload para confirmação de código e cadastro de nova senha."""
    email: EmailStr
    code: str = Field(
        ...,
        min_length=6,
        max_length=6,
        pattern=r"^\d{6}$",
        description="Código numérico de 6 dígitos recebido por e-mail",
    )
    new_password: str = Field(
        ...,
        min_length=6,
        description="Nova senha do usuário (mínimo de 6 caracteres)",
    )
