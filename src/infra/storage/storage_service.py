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

    async def delete(self, key: str) -> None:
        """Remove o objeto do storage. Apagar uma chave inexistente não é erro."""
        ...
