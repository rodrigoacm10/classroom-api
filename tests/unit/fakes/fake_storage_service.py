class FakeStorageService:
    def __init__(
        self,
        return_url: str = "https://fake-r2.dev/evidence/test.jpg",
        url_from_key: bool = False,
    ) -> None:
        self.return_url = return_url
        self.url_from_key = url_from_key
        self.uploaded_files: list[dict] = []
        self.deleted_keys: list[str] = []
        self.copied: list[tuple[str, str]] = []
        self.failing_delete_keys: set[str] = set()
        self.failing_copy_keys: set[str] = set()

    async def upload(self, file_bytes: bytes, key: str, content_type: str) -> str:
        self.uploaded_files.append(
            {
                "key": key,
                "content_type": content_type,
                "size": len(file_bytes),
            }
        )
        return self.public_url(key) if self.url_from_key else self.return_url

    async def delete(self, key: str) -> None:
        if key in self.failing_delete_keys:
            raise RuntimeError(f"Falha simulada ao apagar {key}")
        self.deleted_keys.append(key)

    async def copy(self, source_key: str, destination_key: str) -> None:
        if source_key in self.failing_copy_keys:
            raise RuntimeError(f"Falha simulada ao copiar {source_key}")
        self.copied.append((source_key, destination_key))

    def public_url(self, key: str) -> str:
        return f"https://fake-r2.dev/{key}"
