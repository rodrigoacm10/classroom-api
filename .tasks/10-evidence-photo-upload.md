# Task 10 — Upload de Foto de Evidência na Confirmação de Presença

> **Objetivo**: Permitir que o aluno envie opcionalmente uma foto de evidência (ex: selfie em sala) no
> momento em que confirma a presença. A imagem é armazenada no **Cloudflare R2** e a URL pública
> resultante é vinculada ao campo `evidence_photo_url` do `AttendanceRecord`.
>
> **Entrega esperada desta etapa**:
>
> - `POST /tenants/{tenant_id}/subject-classes/{class_id}/attendance-sessions/{session_id}/confirm`
>   — endpoint existente **estendido** para aceitar `multipart/form-data` com campo `photo` opcional.
> - Upload do arquivo para o Cloudflare R2 via `boto3` (API S3-compatível).
> - URL pública persistida em `AttendanceRecord.evidence_photo_url`.

> [!WARNING]
> **Pré-requisito**: Esta etapa depende diretamente da [Task 6 — Módulo de Chamada](./6-attendance.md)
> e da [Task 7 — Validações de Confirmação](./7-attendance-confirm-validations.md).
> O `ConfirmAttendanceUseCase` já existe e será minimamente estendido para aceitar e repassar a URL
> da foto, sem alterar nenhuma das regras de negócio existentes.

> [!NOTE]
> **Fora do escopo desta etapa:**
>
> - 🔍 **Análise do conteúdo da imagem** (reconhecimento facial, detecção de presença real) — requer
>   integração com Vision AI; fica para etapa futura de segurança avançada.
> - 🔁 **CDN e transformação de imagem** (resize, webp automático) — o Cloudflare R2 suporta via
>   Workers; adicionado em etapa futura de otimização.
> - 🗑️ **Limpeza de arquivos órfãos** (fotos de registros deletados) — lifecycle policy no bucket ou
>   job periódico; adicionado em etapa futura de manutenção.

---

## Conceito Central — Por que a evidência é opcional?

A foto de evidência serve como **ferramenta de auditoria manual**, não como gate obrigatório de acesso.
Torná-la obrigatória:

- Criaria fricção desnecessária para alunos sem câmera funcional ou em redes lentas.
- Não substituiria a validação dupla já existente (GPS + código do dia), que é a defesa principal.

Ela existe para casos onde o registro apresenta **irregularity flags** (GPS impreciso, código confirmado
próximo do horário de expiração, cliente não mobile), dando ao professor evidência visual para a revisão.

```
Fluxo com evidência (quando o aluno envia a foto):

  App Mobile                    API Backend                Cloudflare R2
  ─────────                    ───────────                ─────────────
  multipart/form-data    ──►   1. Valida campos obrig.
  ├── day_code                  2. Valida foto (tipo/tamanho)
  ├── latitude                  3. Upload → R2 via boto3  ──►  PUT /evidence/{key}
  ├── longitude                 4. Recebe URL pública     ◄──  https://r2.../evidence/...
  └── photo (opcional)          5. Executa ConfirmUseCase
                                6. Persiste URL em
                                   AttendanceRecord
                        ◄──    201 Created + record JSON

Fluxo sem evidência (photo não enviada):
  App Mobile                    API Backend
  ─────────                    ───────────
  JSON ou form-data      ──►   1. Valida campos obrig.
  ├── day_code                  2. Executa ConfirmUseCase
  ├── latitude                     (evidence_photo_url = None)
  └── longitude           ◄──  201 Created + record JSON
```

---

## Configuração do Cloudflare R2

### Criação do Bucket no Painel Cloudflare

1. Acesse **[dash.cloudflare.com](https://dash.cloudflare.com/)** → **R2 Object Storage**.
2. Clique em **Create bucket** → nomeie `classroom-evidence` (ou similar).
3. Defina a visibilidade do bucket como **Public** para permitir acesso às URLs sem assinatura temporária.
   - Em **Settings** do bucket → **Public access** → habilitar.
   - Anote a **URL pública do bucket** (ex: `https://pub-XXXX.r2.dev`).

### Geração das Chaves de API

1. Em **R2 → Manage R2 API Tokens** → **Create API Token**.
2. Permissões: **Object Read & Write** para o bucket específico.
3. Anote:
   - `Account ID` (no painel lateral)
   - `Access Key ID`
   - `Secret Access Key`

> [!CAUTION]
> Nunca versione as chaves no Git. Adicione ao `.gitignore`:
> ```
> credentials/
> .env
> ```

### Variáveis de Ambiente

Adicione ao `.env` e ao `.env.example`:

```env
# Cloudflare R2 — Object Storage (evidências fotográficas)
CLOUDFLARE_R2_ACCOUNT_ID=seu_account_id
CLOUDFLARE_R2_ACCESS_KEY_ID=sua_access_key
CLOUDFLARE_R2_SECRET_ACCESS_KEY=sua_secret_key
CLOUDFLARE_R2_BUCKET_NAME=classroom-evidence
CLOUDFLARE_R2_PUBLIC_URL=https://pub-XXXX.r2.dev
```

---

## Arquitetura do Módulo

```
src/
├── config/
│   └── settings.py                                     ← [MODIFY] Adicionar variáveis R2
│
├── infra/
│   └── storage/
│       ├── __init__.py                                 ← [NEW]
│       ├── storage_service.py                          ← [NEW] Protocol/interface StorageService
│       └── r2_storage_service.py                       ← [NEW] Implementação com boto3 + Cloudflare R2
│
└── modules/
    └── attendance/
        ├── application/
        │   └── use_cases/
        │       └── confirm_attendance.py               ← [MODIFY] Aceitar evidence_photo_url opcional
        └── interface/
            ├── router.py                               ← [MODIFY] multipart/form-data + injeção de StorageService
            └── schemas/
                └── record_schemas.py                   ← [MODIFY] ConfirmAttendanceRequest → Form fields

tests/
├── unit/
│   ├── fakes/
│   │   └── fake_storage_service.py                     ← [NEW]
│   └── modules/
│       └── attendance/
│           └── test_confirm_attendance_use_case.py     ← [MODIFY] Casos com/sem foto
└── e2e/
    └── modules/
        └── attendance/
            └── test_attendance_record_router.py        ← [MODIFY] Testar upload de foto (mock R2)
```

---

## Parte 1 — Instalação da Dependência

```bash
uv add boto3
```

O `boto3` é a biblioteca oficial da AWS que o Cloudflare R2 suporta nativamente através de sua
API S3-compatível. Nenhum SDK proprietário da Cloudflare é necessário.

---

## Parte 2 — Configuração (`settings.py`)

```python
# src/config/settings.py (MODIFICAR)
class Settings(BaseSettings):
    # ... campos existentes sem alteração ...

    # Cloudflare R2 — Object Storage
    cloudflare_r2_account_id: str = ""
    cloudflare_r2_access_key_id: str = ""
    cloudflare_r2_secret_access_key: str = ""
    cloudflare_r2_bucket_name: str = "classroom-evidence"
    cloudflare_r2_public_url: str = ""  # Ex: https://pub-XXXX.r2.dev

    @property
    def r2_endpoint_url(self) -> str:
        return f"https://{self.cloudflare_r2_account_id}.r2.cloudflarestorage.com"
```

---

## Parte 3 — Interface de Storage (`storage_service.py`)

Definir uma interface (Protocol) para desacoplar o Use Case da implementação concreta.
Isso permite testar o Use Case com um fake sem precisar de credenciais reais.

```python
# src/infra/storage/storage_service.py (NEW)
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
```

---

## Parte 4 — Implementação R2 (`r2_storage_service.py`)

```python
# src/infra/storage/r2_storage_service.py (NEW)
import asyncio
from functools import partial

import boto3
from botocore.config import Config

from config.settings import settings


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
```

> **Por que `run_in_executor`?**
> O cliente `boto3` é síncrono (bloqueante). Chamá-lo diretamente em uma coroutine travaria o
> event loop do FastAPI, impedindo que outras requisições fossem atendidas simultaneamente.
> O `run_in_executor` delega a chamada para uma thread do pool padrão do Python, mantendo
> a API totalmente responsiva.

---

## Parte 5 — Modificar o Use Case (`confirm_attendance.py`)

O Use Case recebe a URL já processada (upload feito na camada de interface antes da chamada),
mantendo o domínio livre de qualquer dependência de storage.

```python
# src/modules/attendance/application/use_cases/confirm_attendance.py (MODIFY)

@dataclass
class ConfirmAttendanceInput:
    # ... campos existentes sem alteração ...
    evidence_photo_url: str | None = None   # ← [ADD] URL já gerada após upload no R2
```

No método `execute`, repassar o campo para `create_record`:

```python
# dentro de execute(), no return final:
return await self.record_repo.create_record(
    # ... parâmetros existentes sem alteração ...
    evidence_photo_url=data.evidence_photo_url,  # ← [ADD]
)
```

> [!NOTE]
> O Use Case **não sabe o que é R2, S3, boto3 ou upload**. Ele recebe apenas uma `str | None`
> e a persiste. Toda a lógica de storage permanece na camada `infra/storage/`.

---

## Parte 6 — Modificar o Router (`router.py`)

O endpoint de confirmação precisa migrar de `application/json` para `multipart/form-data`
para suportar upload de arquivo. Os campos textuais viram `Form(...)` e a foto vira `UploadFile`.

```python
# src/modules/attendance/interface/router.py (MODIFY)
import uuid
from fastapi import Depends, File, Form, HTTPException, Request, UploadFile, status
from infra.storage.r2_storage_service import R2StorageService

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB


@router.post("/{session_id}/confirm", ...)
async def confirm_attendance(
    tenant_id: UUID,
    subject_class_id: UUID,
    session_id: UUID,
    request: Request,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
    # — Form fields (substituem o body JSON) —
    day_code: str = Form(...),
    latitude: float = Form(...),
    longitude: float = Form(...),
    gps_accuracy_meters: float | None = Form(default=None),
    device_id: str | None = Form(default=None),
    device_info: str | None = Form(default=None),  # JSON string
    # — Upload opcional —
    photo: UploadFile | None = File(default=None),
) -> AttendanceRecordResponse:

    # 1. Processar foto opcional
    evidence_photo_url: str | None = None
    if photo is not None:
        # Validar tipo MIME
        if photo.content_type not in ALLOWED_CONTENT_TYPES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Tipo de arquivo não suportado: {photo.content_type}. Use JPEG, PNG ou WebP.",
            )
        file_bytes = await photo.read()

        # Validar tamanho
        if len(file_bytes) > MAX_FILE_SIZE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="Arquivo muito grande. Tamanho máximo: 5 MB.",
            )

        # Gerar chave única no bucket: evidence/{session_id}/{uuid}.{ext}
        extension = photo.content_type.split("/")[-1]
        key = f"evidence/{session_id}/{uuid.uuid4()}.{extension}"

        # Upload para o Cloudflare R2
        storage = R2StorageService()
        evidence_photo_url = await storage.upload(
            file_bytes=file_bytes,
            key=key,
            content_type=photo.content_type,
        )

    # 2. Executar Use Case (sem mudança na lógica de negócio)
    record = await use_case.execute(
        ConfirmAttendanceInput(
            # ... parâmetros existentes sem alteração ...
            evidence_photo_url=evidence_photo_url,
        )
    )
    return AttendanceRecordResponse.model_validate(record)
```

---

## Parte 7 — Estrutura da Chave no Bucket (Key Strategy)

A chave do arquivo no bucket segue o padrão:

```
evidence/{session_id}/{uuid}.{ext}
```

| Componente    | Exemplo            | Motivo                                                              |
| ------------- | ------------------ | ------------------------------------------------------------------- |
| `evidence/`   | prefixo fixo       | Facilita lifecycle policies e permissões granulares no bucket       |
| `{session_id}`| `3fa85f64-...`     | Agrupa fotos por chamada — facilita auditoria e limpeza futura      |
| `{uuid}`      | `a1b2c3d4-...`     | UUID novo gerado na API — garante unicidade mesmo em retry do aluno |
| `.{ext}`      | `.jpg`, `.png`     | Preserva o Content-Type original para o browser abrir corretamente  |

**URL pública resultante**:
```
https://pub-XXXX.r2.dev/evidence/3fa85f64-.../a1b2c3d4-....jpg
```

---

## Parte 8 — Como Testar

### 8.1 Testes de Unidade (Use Case)

Os testes de unidade **não precisam de Cloudflare R2 real**. O Use Case aceita apenas a URL como string.

```python
# tests/unit/modules/attendance/test_confirm_attendance_use_case.py (MODIFY)

async def test_confirm_attendance_with_evidence_photo():
    """Evidência opcional: quando fornecida, deve ser persistida no record."""
    photo_url = "https://pub-xxx.r2.dev/evidence/session-id/uuid.jpg"
    input_data = ConfirmAttendanceInput(
        # ... campos obrigatórios ...
        evidence_photo_url=photo_url,
    )

    record = await use_case.execute(input_data)

    assert record.evidence_photo_url == photo_url


async def test_confirm_attendance_without_evidence_photo():
    """Evidência opcional: quando não fornecida, campo deve ser None."""
    input_data = ConfirmAttendanceInput(
        # ... campos obrigatórios ...
        evidence_photo_url=None,
    )

    record = await use_case.execute(input_data)

    assert record.evidence_photo_url is None
```

### 8.2 Fake do StorageService (para testes sem R2 real)

```python
# tests/unit/fakes/fake_storage_service.py (NEW)
class FakeStorageService:
    def __init__(self, return_url: str = "https://fake-r2.dev/evidence/test.jpg"):
        self.return_url = return_url
        self.uploaded_files: list[dict] = []

    async def upload(self, file_bytes: bytes, key: str, content_type: str) -> str:
        self.uploaded_files.append({
            "key": key,
            "content_type": content_type,
            "size": len(file_bytes),
        })
        return self.return_url
```

### 8.3 Testes E2E do Router (Mock do R2)

Nos testes E2E, o cliente real do R2 é substituído por mock via `unittest.mock.patch`:

```python
# tests/e2e/modules/attendance/test_attendance_record_router.py (MODIFY)
from unittest.mock import AsyncMock, patch

FAKE_R2_URL = "https://pub-test.r2.dev/evidence/session-id/uuid.jpg"


async def test_confirm_attendance_with_photo_upload(client, ...):
    """Upload de foto opcional retorna evidence_photo_url no response."""
    with patch("modules.attendance.interface.router.R2StorageService") as MockR2:
        instance = MockR2.return_value
        instance.upload = AsyncMock(return_value=FAKE_R2_URL)

        response = await client.post(
            f"/tenants/{tenant_id}/subject-classes/{class_id}"
            f"/attendance-sessions/{session_id}/confirm",
            data={
                "day_code": session.day_code,
                "latitude": str(room_lat),
                "longitude": str(room_lng),
            },
            files={"photo": ("selfie.jpg", b"fake-jpeg-bytes", "image/jpeg")},
            headers={"Authorization": f"Bearer {student_token}"},
        )

    assert response.status_code == 201
    assert response.json()["evidence_photo_url"] == FAKE_R2_URL


async def test_confirm_attendance_without_photo(client, ...):
    """Confirmação sem foto deve funcionar com evidence_photo_url = null."""
    response = await client.post(
        f"/tenants/{tenant_id}/subject-classes/{class_id}"
        f"/attendance-sessions/{session_id}/confirm",
        data={
            "day_code": session.day_code,
            "latitude": str(room_lat),
            "longitude": str(room_lng),
        },
        headers={"Authorization": f"Bearer {student_token}"},
    )

    assert response.status_code == 201
    assert response.json()["evidence_photo_url"] is None


async def test_confirm_attendance_photo_invalid_mime_type(client, ...):
    """Tipo MIME não suportado deve retornar 422."""
    response = await client.post(
        ...,
        data={...},
        files={"photo": ("document.pdf", b"fake-pdf", "application/pdf")},
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert response.status_code == 422


async def test_confirm_attendance_photo_too_large(client, ...):
    """Arquivo maior que 5 MB deve retornar 413."""
    big_file = b"x" * (5 * 1024 * 1024 + 1)
    response = await client.post(
        ...,
        data={...},
        files={"photo": ("big.jpg", big_file, "image/jpeg")},
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert response.status_code == 413
```

### 8.4 Teste Manual via cURL

```bash
# Confirmar presença COM foto de evidência
curl -X POST \
  "http://localhost:8000/tenants/{tenant_id}/subject-classes/{class_id}/attendance-sessions/{session_id}/confirm" \
  -H "Authorization: Bearer {student_jwt}" \
  -F "day_code=ABC123" \
  -F "latitude=-23.5505" \
  -F "longitude=-46.6333" \
  -F "photo=@/caminho/para/selfie.jpg;type=image/jpeg"

# Confirmar presença SEM foto (campo photo ausente — behaviour padrão)
curl -X POST \
  "http://localhost:8000/tenants/{tenant_id}/subject-classes/{class_id}/attendance-sessions/{session_id}/confirm" \
  -H "Authorization: Bearer {student_jwt}" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "day_code=ABC123&latitude=-23.5505&longitude=-46.6333"
```

### 8.5 Verificar no Painel R2

Após um teste manual com foto real:
1. Acesse **Cloudflare Dashboard → R2 → classroom-evidence**.
2. Navegue até `evidence/{session_id}/`.
3. Confirme que o arquivo foi criado com o nome UUID correto.
4. Clique no arquivo e acesse a **URL pública** para verificar que a imagem é renderizável no browser.

---

## Checklist de Implementação

- [ ] Instalar dependência: `uv add boto3`
- [ ] Adicionar variáveis R2 em `settings.py` e `.env.example`
- [ ] Criar `src/infra/storage/__init__.py`
- [ ] Criar `src/infra/storage/storage_service.py` (Protocol)
- [ ] Criar `src/infra/storage/r2_storage_service.py` (implementação boto3)
- [ ] Modificar `ConfirmAttendanceInput` — adicionar `evidence_photo_url: str | None = None`
- [ ] Modificar `ConfirmAttendanceUseCase.execute()` — repassar campo para `create_record`
- [ ] Modificar `router.py` — migrar para `multipart/form-data`, upload e validações
- [ ] Criar `tests/unit/fakes/fake_storage_service.py`
- [ ] Atualizar testes de unidade do Use Case — cenários com e sem foto
- [ ] Atualizar testes E2E — foto com mock R2, sem foto, MIME inválido, arquivo grande
- [ ] Testar manualmente com cURL e verificar no painel Cloudflare R2
