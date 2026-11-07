import asyncio

from pwdlib import PasswordHash

pwd_context = PasswordHash.recommended()


def hash_password(plain_password: str) -> str:
    """Retorna o hash seguro da senha (versão síncrona para seeds/testes)."""
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Retorna True se a senha bate com o hash (versão síncrona para seeds/testes)."""
    return pwd_context.verify(plain_password, hashed_password)


async def hash_password_async(plain_password: str) -> str:
    """Calcula o hash da senha em thread separada sem bloquear o Event Loop do FastAPI."""
    return await asyncio.to_thread(pwd_context.hash, plain_password)


async def verify_password_async(plain_password: str, hashed_password: str) -> bool:
    """Verifica o hash da senha em thread separada sem bloquear o Event Loop do FastAPI."""
    return await asyncio.to_thread(pwd_context.verify, plain_password, hashed_password)
