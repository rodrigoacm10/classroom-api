import pytest


@pytest.fixture(scope="session")
def anyio_backend():
    """Garante que pytest-asyncio use asyncio como backend."""
    return "asyncio"
