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

    async def copy(self, source_key: str, destination_key: str) -> None:
        """Copia um objeto dentro do storage. Falha se a origem não existir."""
        ...

    def public_url(self, key: str) -> str:
        """URL pública de uma chave. É só montar o texto, sem acesso à rede."""
        ...
