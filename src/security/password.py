from pwdlib import PasswordHash

pwd_context = PasswordHash.recommended()


def hash_password(plain_password: str) -> str:
    """Retorna o hash seguro da senha."""
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Retorna True se a senha bate com o hash."""
    return pwd_context.verify(plain_password, hashed_password)
