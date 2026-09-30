from typing import Protocol


class StorageService(Protocol):
    async def upload(
        self,
        file_bytes: bytes,
        key: str,
        content_type: str,
    ) -> str:
        """Faz upload do arquivo e retorna a URL pública."""
        ...