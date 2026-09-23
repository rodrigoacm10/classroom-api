from uuid import UUID, uuid4

from infra.storage.storage_service import StorageService
from shared.exceptions import BusinessRuleException

ALLOWED_EVIDENCE_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_EVIDENCE_FILE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB


async def upload_evidence_photo(
    storage_service: StorageService,
    session_id: UUID,
    file_bytes: bytes,
    content_type: str,
) -> str:
    """
    Valida e envia uma foto de evidência de presença para o storage configurado,
    retornando a URL pública gerada.
    """
    if content_type not in ALLOWED_EVIDENCE_CONTENT_TYPES:
        raise BusinessRuleException(
            f"Tipo de arquivo não suportado: {content_type}. Use JPEG, PNG ou WebP."
        )
    if len(file_bytes) > MAX_EVIDENCE_FILE_SIZE_BYTES:
        raise BusinessRuleException("Arquivo muito grande. Tamanho máximo: 5 MB.")

    extension = content_type.split("/")[-1]
    key = f"evidence/{session_id}/{uuid4()}.{extension}"

    return await storage_service.upload(
        file_bytes=file_bytes,
        key=key,
        content_type=content_type,
    )