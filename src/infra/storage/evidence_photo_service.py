from dataclasses import dataclass
from uuid import UUID, uuid4

from infra.storage.storage_service import StorageService
from shared.exceptions import BusinessRuleException

ALLOWED_EVIDENCE_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_EVIDENCE_FILE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB

# Fotos recém-enviadas ficam em pending/ até a presença ser confirmada. Depois, são
# promovidas para confirmed/. A lifecycle policy do bucket só atua em pending/.
PENDING_PREFIX = "pending/"
CONFIRMED_PREFIX = "confirmed/"


@dataclass
class UploadedEvidencePhoto:
    key: str
    url: str


def confirmed_key_for(key: str) -> str:
    """
    Chave definitiva de uma foto: troca o prefixo pending/ por confirmed/.
    Chaves fora de pending/ (uploads antigos, gravados em evidence/) já são definitivas
    e voltam sem alteração. Quem chama detecta que não há o que copiar comparando
    o resultado com a chave original.
    """
    if key.startswith(PENDING_PREFIX):
        return CONFIRMED_PREFIX + key[len(PENDING_PREFIX) :]
    return key


async def upload_evidence_photo(
    storage_service: StorageService,
    session_id: UUID,
    file_bytes: bytes,
    content_type: str,
) -> UploadedEvidencePhoto:
    """
    Valida e envia uma foto de evidência de presença para o storage configurado,
    retornando a chave do objeto no bucket e a URL pública gerada.
    """
    if content_type not in ALLOWED_EVIDENCE_CONTENT_TYPES:
        raise BusinessRuleException(
            f"Tipo de arquivo não suportado: {content_type}. Use JPEG, PNG ou WebP."
        )
    if len(file_bytes) > MAX_EVIDENCE_FILE_SIZE_BYTES:
        raise BusinessRuleException("Arquivo muito grande. Tamanho máximo: 5 MB.")

    extension = content_type.split("/")[-1]
    key = f"{PENDING_PREFIX}{session_id}/{uuid4()}.{extension}"

    url = await storage_service.upload(
        file_bytes=file_bytes,
        key=key,
        content_type=content_type,
    )
    return UploadedEvidencePhoto(key=key, url=url)
