class FakeStorageService:
    def __init__(self, return_url: str = "https://fake-r2.dev/evidence/test.jpg") -> None:
        self.return_url = return_url
        self.uploaded_files: list[dict] = []

    async def upload(self, file_bytes: bytes, key: str, content_type: str) -> str:
        self.uploaded_files.append(
            {
                "key": key,
                "content_type": content_type,
                "size": len(file_bytes),
            }
        )
        return self.return_url