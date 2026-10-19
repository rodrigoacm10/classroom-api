import asyncio
import logging
from functools import partial

import boto3
from botocore.config import Config

from config.settings import settings

logger = logging.getLogger(__name__)



class R2StorageService:
    def __init__(self) -> None:
        self._client = boto3.client(
            "s3",
            endpoint_url=settings.r2_endpoint_url,
            aws_access_key_id=settings.cloudflare_r2_access_key_id,
            aws_secret_access_key=settings.cloudflare_r2_secret_access_key,
            config=Config(signature_version="s3v4"),
            region_name="auto",
        )
        self._bucket = settings.cloudflare_r2_bucket_name
        self._public_url = settings.cloudflare_r2_public_url.rstrip("/")

    async def upload(
        self,
        file_bytes: bytes,
        key: str,
        content_type: str,
    ) -> str:
        """
        Faz upload dos bytes para o bucket R2 e retorna a URL pública.
        Executa o upload síncrono do boto3 em uma thread separada para
        não bloquear o event loop do FastAPI/asyncio.
        """
        loop = asyncio.get_event_loop()
        put_fn = partial(
            self._client.put_object,
            Bucket=self._bucket,
            Key=key,
            Body=file_bytes,
            ContentType=content_type,
        )
        await loop.run_in_executor(None, put_fn)
        return f"{self._public_url}/{key}"

    async def delete(self, key: str) -> None:
        """
        Remove o objeto do bucket R2. Como o upload, roda o boto3 (síncrono)
        em uma thread separada para não bloquear o event loop.
        """
        loop = asyncio.get_running_loop()
        delete_fn = partial(
            self._client.delete_object,
            Bucket=self._bucket,
            Key=key,
        )
        try:
            await loop.run_in_executor(None, delete_fn)
        except Exception as exc:
            logger.error("Erro ao apagar objeto %s do R2: %s", key, exc)
            raise
