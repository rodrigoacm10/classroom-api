# Task 3 — Módulo de Salas com Validação Geoespacial (PostGIS)

> **Objetivo**: Implementar o cadastro e gerenciamento de Salas (`Room`) de uma
> Tenant/Instituição. Cada sala possui um **ponto central de localização** (latitude e
> longitude, armazenados como `GEOGRAPHY(Point, 4326)` no PostgreSQL via PostGIS) e um
> **raio de tolerância em metros** que define a circunferência de efeito para validação
> de presença.
>
> **Entrega esperada**: `POST /tenants/{tenant_id}/rooms`,
> `GET /tenants/{tenant_id}/rooms`, `GET /tenants/{tenant_id}/rooms/{room_id}`,
> `PATCH /tenants/{tenant_id}/rooms/{room_id}`,
> `DELETE /tenants/{tenant_id}/rooms/{room_id}`.

---

## Conceito central — geolocalização com PostGIS

### Por que não usar dois campos `FLOAT` (latitude e longitude)?

Armazenar coordenadas geográficas como campos numéricos simples funciona para casos
triviais, mas **não é o padrão da indústria** e apresenta limitações críticas:

| Problema                          | `FLOAT` puro                                          | `GEOGRAPHY(Point)` PostGIS         |
|-----------------------------------|-------------------------------------------------------|------------------------------------|
| Cálculo de distância              | Implementação manual (Haversine em Python — impreciso) | `ST_DWithin` / `ST_Distance` nativos, geodésicos e precisos |
| Performance em escala             | Full scan da tabela a cada query                       | Índice espacial **GiST** — O(log n) |
| Consulta "aluno dentro do raio"   | Impossível em SQL sem calcular tudo em memória         | Uma única cláusula SQL com `ST_DWithin` |
| Padrão de mercado                 | Não — é improvisação                                   | Sim — Google Maps, Uber, Airbnb, iFood |

### Modelo mental: ponto + circunferência

```
         tolerance_radius_meters = 50m
                 ↓
         ●───────────────────
         │                  │
         │  SALA 204         │  ← room.location (GEOGRAPHY Point)
         │  lat: -8.0476     │
         │  lon: -34.8770    │
         │                  │
         ───────────────────●

Quando o aluno confirma presença:
  - App envia: { latitude: -8.0477, longitude: -34.8771 }
  - Backend executa:
      ST_DWithin(room.location, aluno_point, 50)
        → true  ✅ dentro do raio
        → false ❌ fora do raio
```

### O SRID 4326 (WGS84)

O número `4326` é o **SRID (Spatial Reference ID)** que identifica o sistema de
coordenadas GPS padrão mundial (WGS84). É o mesmo sistema usado pelo GPS do celular
do aluno. Toda coordenada enviada pelo app (`latitude`, `longitude`) já está nesse
sistema — não é necessária nenhuma conversão.

> **Atenção — ordem dos eixos no PostGIS**: o padrão PostGIS para `POINT` é
> `POINT(longitude latitude)` — ou seja, **X = longitude, Y = latitude**
> (contraintuitivo, mas é o padrão GeoJSON e PostGIS). O GeoAlchemy2 abstrai isso,
> mas é importante saber ao escrever SQL direto.

---

## Visão geral da ordem de implementação

```
infra/database/models/room.py                ← 1. Model SQLAlchemy RoomModel (com GEOGRAPHY)
        │
alembic/versions/XXX_create_rooms_table.py   ← 2. Migration (habilitar PostGIS + criar tabela + índice GiST)
        │
modules/room/
  domain/entities/room.py                    ← 3. Entidade de domínio Room
  domain/repositories/room_repository.py     ← 4. Protocol (interface) do repositório
  infra/mappers/room_mapper.py               ← 5. Mapper Model ↔ Entity
  infra/repositories/room_sqlalchemy_repository.py  ← 6. Implementação SQLAlchemy
  application/use_cases/create_room.py       ← 7. CreateRoomUseCase
  application/use_cases/get_room.py          ← 8. GetRoomUseCase
  application/use_cases/list_rooms.py        ← 9. ListRoomsUseCase
  application/use_cases/update_room.py       ← 10. UpdateRoomUseCase
  application/use_cases/delete_room.py       ← 11. DeleteRoomUseCase
  interface/schemas/room_schemas.py          ← 12. Schemas Pydantic (request/response)
  interface/room_router.py                   ← 13. Router HTTP com 5 rotas
        │
main.py                                      ← 14. Registrar o router na aplicação
tests/                                       ← 15. Testes unitários, integração e E2E
```

---

## Passo 0 — Instalar dependência e habilitar PostGIS

### Instalar GeoAlchemy2

```bash
uv add geoalchemy2
```

### Habilitar extensão PostGIS no banco (executar uma única vez)

No **SQL Editor do Neon** (ou via `psql`), executar:

```sql
CREATE EXTENSION IF NOT EXISTS postgis;
```

> **Nota**: No Neon (free tier), o PostGIS já está disponível nativamente.
> Basta ativar a extensão. Não é necessário nenhuma instalação adicional.

---

## Passo 1 — Model SQLAlchemy `RoomModel`

```python
# src/infra/database/models/room.py
import uuid
from datetime import datetime

from geoalchemy2 import Geography
from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from infra.database.base import Base


class RoomModel(Base):
    __tablename__ = "rooms"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    # Ponto central da sala em coordenadas geodésicas (GPS / WGS84)
    # GEOGRAPHY calcula distâncias em metros na superfície terrestre curva
    location: Mapped[str] = mapped_column(
        Geography(geometry_type="POINT", srid=4326), nullable=False
    )

    # Raio de tolerância em metros — define a circunferência de presença válida
    tolerance_radius_meters: Mapped[int] = mapped_column(
        Integer, nullable=False, default=50
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
```

> **Notas de design:**
> - `Geography` (não `Geometry`) usa coordenadas geodésicas — distâncias em metros reais.
> - `srid=4326` corresponde ao WGS84, o sistema de coordenadas GPS padrão global.
> - `ondelete="CASCADE"` garante que ao deletar a tenant, todas as suas salas são removidas.
> - `created_by` usa `ondelete="SET NULL"` para preservar o histórico da sala.
> - `tolerance_radius_meters` tem default de 50 metros — raio razoável para uma sala de aula.

---

## Passo 2 — Migration Alembic

A migration deve:
1. Garantir que a extensão PostGIS está ativa (idempotente).
2. Criar a tabela `rooms`.
3. Criar o **índice espacial GiST** na coluna `location` — fundamental para performance.

```bash
uv run alembic revision --autogenerate -m "create rooms table with postgis geography"
uv run alembic upgrade head
```

A migration criará (aproximadamente):

```sql
-- Garante que PostGIS está ativo
CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE rooms (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    created_by               UUID REFERENCES users(id) ON DELETE SET NULL,
    name                     VARCHAR(255) NOT NULL,
    location                 GEOGRAPHY(POINT, 4326) NOT NULL,
    tolerance_radius_meters  INTEGER NOT NULL DEFAULT 50,
    created_at               TIMESTAMPTZ DEFAULT now(),
    updated_at               TIMESTAMPTZ DEFAULT now()
);

-- Índice espacial GiST — torna ST_DWithin e ST_Distance O(log n) ao invés de O(n)
CREATE INDEX idx_rooms_location ON rooms USING GIST(location);

-- Índice comum para filtrar por tenant
CREATE INDEX idx_rooms_tenant_id ON rooms(tenant_id);
```

> **Por que o índice GiST é obrigatório?**
> Sem ele, cada consulta de validação de presença fará um full scan da tabela de salas.
> Com ele, o PostgreSQL usa uma estrutura de árvore espacial (R-tree generalizado) para
> encontrar salas candidatas em O(log n). Esse índice é **o** componente de otimização
> geoespacial que o TCC precisa demonstrar.

---

## Passo 3 — Entidade de Domínio `Room`

A entidade de domínio trabalha com tipos Python nativos (`float` para lat/lon).
A conversão para o formato PostGIS (WKT/WKB) é responsabilidade da camada de infra.

```python
# src/modules/room/domain/entities/room.py
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID, uuid4


@dataclass
class Room:
    tenant_id: UUID
    name: str
    latitude: float          # eixo Y — ex: -8.0476  (intervalo: -90.0 a 90.0)
    longitude: float         # eixo X — ex: -34.8770 (intervalo: -180.0 a 180.0)
    tolerance_radius_meters: int = 50
    created_by: UUID | None = None
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def is_within_radius(self, latitude: float, longitude: float) -> bool:
        """
        Verificação aproximada em Python (apenas para testes unitários puros).
        A validação real e performática usa ST_DWithin no repositório SQLAlchemy.
        Fórmula de Haversine — precisa para distâncias curtas (< 1 km).
        """
        import math

        R = 6_371_000  # raio médio da Terra em metros

        lat1, lon1 = math.radians(self.latitude), math.radians(self.longitude)
        lat2, lon2 = math.radians(latitude), math.radians(longitude)

        dlat = lat2 - lat1
        dlon = lon2 - lon1

        a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        distance_meters = R * 2 * math.asin(math.sqrt(a))

        return distance_meters <= self.tolerance_radius_meters
```

> **Notas de design:**
> - A entidade armazena `latitude` e `longitude` como `float` — tipos nativos Python.
> - O método `is_within_radius` existe **apenas para testes unitários** (sem banco).
> - A validação de presença em produção usa `ST_DWithin` no repositório para precisão
>   geodésica e performance com índice GiST.

---

## Passo 4 — Interface do Repositório (Protocol)

```python
# src/modules/room/domain/repositories/room_repository.py
from typing import Protocol
from uuid import UUID

from modules.room.domain.entities.room import Room


class RoomRepository(Protocol):

    async def save(self, room: Room) -> Room: ...

    async def find_by_id(self, room_id: UUID) -> Room | None: ...

    async def find_by_id_and_tenant(
        self, room_id: UUID, tenant_id: UUID
    ) -> Room | None: ...

    async def list_by_tenant(self, tenant_id: UUID) -> list[Room]: ...

    async def delete(self, room: Room) -> None: ...
```

---

## Passo 5 — Mapper `RoomMapper`

O mapper é responsável pela conversão entre o tipo `GEOGRAPHY` do PostGIS
(retornado como string WKB hexadecimal pelo SQLAlchemy/GeoAlchemy2) e
os campos `latitude`/`longitude` da entidade de domínio.

```python
# src/modules/room/infra/mappers/room_mapper.py
from geoalchemy2.shape import to_shape
from geoalchemy2.elements import WKTElement
from shapely.geometry import Point

from infra.database.models.room import RoomModel
from modules.room.domain.entities.room import Room


class RoomMapper:

    @staticmethod
    def to_domain(model: RoomModel) -> Room:
        # Converte GEOGRAPHY (WKB) → shapely Point → lat/lon
        point: Point = to_shape(model.location)
        return Room(
            id=model.id,
            tenant_id=model.tenant_id,
            created_by=model.created_by,
            name=model.name,
            latitude=point.y,   # shapely: y = latitude
            longitude=point.x,  # shapely: x = longitude
            tolerance_radius_meters=model.tolerance_radius_meters,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    @staticmethod
    def to_model(entity: Room) -> RoomModel:
        # Converte lat/lon → WKT no formato PostGIS: POINT(longitude latitude)
        wkt = WKTElement(f"POINT({entity.longitude} {entity.latitude})", srid=4326)
        return RoomModel(
            id=entity.id,
            tenant_id=entity.tenant_id,
            created_by=entity.created_by,
            name=entity.name,
            location=wkt,
            tolerance_radius_meters=entity.tolerance_radius_meters,
        )
```

> **Ordem dos eixos — ponto crítico**:
> - PostGIS / GeoJSON: `POINT(longitude latitude)` → X = longitude, Y = latitude
> - Shapely (biblioteca Python): `point.x = longitude`, `point.y = latitude`
> - Sempre que escrever `POINT(...)` manualmente, coloque **longitude primeiro**.

---

## Passo 6 — Repositório SQLAlchemy

```python
# src/modules/room/infra/repositories/room_sqlalchemy_repository.py
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from infra.database.models.room import RoomModel
from modules.room.domain.entities.room import Room
from modules.room.infra.mappers.room_mapper import RoomMapper


class RoomSQLAlchemyRepository:

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def save(self, room: Room) -> Room:
        model = RoomMapper.to_model(room)
        merged = await self.session.merge(model)
        await self.session.commit()
        await self.session.refresh(merged)
        return RoomMapper.to_domain(merged)

    async def find_by_id(self, room_id: UUID) -> Room | None:
        stmt = select(RoomModel).where(RoomModel.id == room_id)
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        return RoomMapper.to_domain(model) if model else None

    async def find_by_id_and_tenant(
        self, room_id: UUID, tenant_id: UUID
    ) -> Room | None:
        stmt = select(RoomModel).where(
            RoomModel.id == room_id,
            RoomModel.tenant_id == tenant_id,
        )
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        return RoomMapper.to_domain(model) if model else None

    async def list_by_tenant(self, tenant_id: UUID) -> list[Room]:
        stmt = select(RoomModel).where(RoomModel.tenant_id == tenant_id)
        result = await self.session.execute(stmt)
        return [RoomMapper.to_domain(m) for m in result.scalars().all()]

    async def delete(self, room: Room) -> None:
        model = await self.session.get(RoomModel, room.id)
        if model:
            await self.session.delete(model)
            await self.session.commit()
```

---

## Passo 7 — `CreateRoomUseCase`

```python
# src/modules/room/application/use_cases/create_room.py
from dataclasses import dataclass
from uuid import UUID

from modules.room.domain.entities.room import Room
from modules.room.domain.repositories.room_repository import RoomRepository
from modules.tenant.domain.repositories.tenant_repository import TenantRepository
from shared.exceptions import ResourceNotFoundException


@dataclass
class CreateRoomInput:
    tenant_id: UUID
    name: str
    latitude: float
    longitude: float
    tolerance_radius_meters: int = 50
    created_by: UUID | None = None


class CreateRoomUseCase:

    def __init__(
        self,
        room_repo: RoomRepository,
        tenant_repo: TenantRepository,
    ) -> None:
        self.room_repo = room_repo
        self.tenant_repo = tenant_repo

    async def execute(self, data: CreateRoomInput) -> Room:
        # 1. Verificar se a tenant existe e não está deletada
        tenant = await self.tenant_repo.find_by_id(data.tenant_id)
        if not tenant or tenant.deleted:
            raise ResourceNotFoundException("Instituição/tenant não encontrada.")

        # 2. Criar a entidade Room com as coordenadas fornecidas
        room = Room(
            tenant_id=data.tenant_id,
            name=data.name,
            latitude=data.latitude,
            longitude=data.longitude,
            tolerance_radius_meters=data.tolerance_radius_meters,
            created_by=data.created_by,
        )

        # 3. Persistir e retornar
        return await self.room_repo.save(room)
```

**Regras de negócio validadas:**
- Tenant existe e não está deletada → `ResourceNotFoundException`

---

## Passo 8 — `GetRoomUseCase`

```python
# src/modules/room/application/use_cases/get_room.py
from dataclasses import dataclass
from uuid import UUID

from modules.room.domain.entities.room import Room
from modules.room.domain.repositories.room_repository import RoomRepository
from shared.exceptions import ResourceNotFoundException


@dataclass
class GetRoomInput:
    room_id: UUID
    tenant_id: UUID


class GetRoomUseCase:

    def __init__(self, room_repo: RoomRepository) -> None:
        self.room_repo = room_repo

    async def execute(self, data: GetRoomInput) -> Room:
        room = await self.room_repo.find_by_id_and_tenant(
            room_id=data.room_id,
            tenant_id=data.tenant_id,
        )
        if not room:
            raise ResourceNotFoundException("Sala não encontrada.")
        return room
```

---

## Passo 9 — `ListRoomsUseCase`

```python
# src/modules/room/application/use_cases/list_rooms.py
from dataclasses import dataclass
from uuid import UUID

from modules.room.domain.entities.room import Room
from modules.room.domain.repositories.room_repository import RoomRepository
from modules.tenant.domain.repositories.tenant_repository import TenantRepository
from shared.exceptions import ResourceNotFoundException


@dataclass
class ListRoomsInput:
    tenant_id: UUID


class ListRoomsUseCase:

    def __init__(
        self,
        room_repo: RoomRepository,
        tenant_repo: TenantRepository,
    ) -> None:
        self.room_repo = room_repo
        self.tenant_repo = tenant_repo

    async def execute(self, data: ListRoomsInput) -> list[Room]:
        tenant = await self.tenant_repo.find_by_id(data.tenant_id)
        if not tenant or tenant.deleted:
            raise ResourceNotFoundException("Instituição/tenant não encontrada.")

        return await self.room_repo.list_by_tenant(data.tenant_id)
```

---

## Passo 10 — `UpdateRoomUseCase`

```python
# src/modules/room/application/use_cases/update_room.py
from dataclasses import dataclass
from uuid import UUID

from modules.room.domain.entities.room import Room
from modules.room.domain.repositories.room_repository import RoomRepository
from shared.exceptions import ResourceNotFoundException


@dataclass
class UpdateRoomInput:
    room_id: UUID
    tenant_id: UUID
    name: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    tolerance_radius_meters: int | None = None


class UpdateRoomUseCase:

    def __init__(self, room_repo: RoomRepository) -> None:
        self.room_repo = room_repo

    async def execute(self, data: UpdateRoomInput) -> Room:
        # 1. Buscar a sala garantindo que pertence à tenant correta
        room = await self.room_repo.find_by_id_and_tenant(
            room_id=data.room_id,
            tenant_id=data.tenant_id,
        )
        if not room:
            raise ResourceNotFoundException("Sala não encontrada.")

        # 2. Aplicar apenas os campos fornecidos (PATCH semântico)
        if data.name is not None:
            room.name = data.name
        if data.latitude is not None:
            room.latitude = data.latitude
        if data.longitude is not None:
            room.longitude = data.longitude
        if data.tolerance_radius_meters is not None:
            room.tolerance_radius_meters = data.tolerance_radius_meters

        # 3. Persiste e retorna
        return await self.room_repo.save(room)
```

> **Notas de design:**
> - Semântica de PATCH: apenas os campos enviados pelo cliente são alterados.
> - `latitude` e `longitude` podem ser atualizados individualmente, mas o mapper
>   sempre persiste ambos juntos como um único `POINT(lon lat)`.

---

## Passo 11 — `DeleteRoomUseCase`

```python
# src/modules/room/application/use_cases/delete_room.py
from dataclasses import dataclass
from uuid import UUID

from modules.room.domain.repositories.room_repository import RoomRepository
from shared.exceptions import ResourceNotFoundException


@dataclass
class DeleteRoomInput:
    room_id: UUID
    tenant_id: UUID


class DeleteRoomUseCase:

    def __init__(self, room_repo: RoomRepository) -> None:
        self.room_repo = room_repo

    async def execute(self, data: DeleteRoomInput) -> None:
        room = await self.room_repo.find_by_id_and_tenant(
            room_id=data.room_id,
            tenant_id=data.tenant_id,
        )
        if not room:
            raise ResourceNotFoundException("Sala não encontrada.")

        await self.room_repo.delete(room)
```

> **Nota**: Salas são deletadas fisicamente (hard delete). Soft delete não se aplica aqui
> pois as salas são entidades de configuração — não há histórico que dependa delas
> diretamente. Sessões de chamada referenciam a sala por ID e serão afetadas se a sala
> for deletada (considerar `ondelete="RESTRICT"` nas sessões ao implementar o módulo de chamadas).

---

## Passo 12 — Schemas Pydantic

```python
# src/modules/room/interface/schemas/room_schemas.py
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class CreateRoomRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, examples=["Sala 204"])
    latitude: float = Field(
        ...,
        ge=-90.0,
        le=90.0,
        description="Latitude do ponto central da sala (WGS84 / GPS). Intervalo: -90.0 a 90.0.",
        examples=[-8.0476],
    )
    longitude: float = Field(
        ...,
        ge=-180.0,
        le=180.0,
        description="Longitude do ponto central da sala (WGS84 / GPS). Intervalo: -180.0 a 180.0.",
        examples=[-34.8770],
    )
    tolerance_radius_meters: int = Field(
        default=50,
        ge=5,
        le=500,
        description="Raio de tolerância em metros. Define a circunferência de presença válida ao redor do ponto central.",
        examples=[50],
    )


class UpdateRoomRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    latitude: float | None = Field(default=None, ge=-90.0, le=90.0)
    longitude: float | None = Field(default=None, ge=-180.0, le=180.0)
    tolerance_radius_meters: int | None = Field(default=None, ge=5, le=500)


class RoomResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    created_by: UUID | None
    name: str
    latitude: float
    longitude: float
    tolerance_radius_meters: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
```

> **Notas de validação:**
> - `latitude` validada entre -90.0 e 90.0 (limites geodésicos do eixo Y).
> - `longitude` validada entre -180.0 e 180.0 (limites geodésicos do eixo X).
> - `tolerance_radius_meters` limitado entre 5m (mínimo funcional) e 500m (segurança contra configurações absurdas).

---

## Passo 13 — Router HTTP

```python
# src/modules/room/interface/room_router.py
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from infra.database.session import get_db
from modules.room.application.use_cases.create_room import CreateRoomInput, CreateRoomUseCase
from modules.room.application.use_cases.delete_room import DeleteRoomInput, DeleteRoomUseCase
from modules.room.application.use_cases.get_room import GetRoomInput, GetRoomUseCase
from modules.room.application.use_cases.list_rooms import ListRoomsInput, ListRoomsUseCase
from modules.room.application.use_cases.update_room import UpdateRoomInput, UpdateRoomUseCase
from modules.room.infra.repositories.room_sqlalchemy_repository import RoomSQLAlchemyRepository
from modules.room.interface.schemas.room_schemas import (
    CreateRoomRequest,
    RoomResponse,
    UpdateRoomRequest,
)
from modules.tenant.infra.repositories.tenant_sqlalchemy_repository import TenantSQLAlchemyRepository
from modules.user.domain.entities.user import User
from security.dependencies.current_user import get_current_user
from security.dependencies.require_role import require_role
from shared.enums.user_role import UserRole

router = APIRouter(prefix="/tenants/{tenant_id}/rooms", tags=["rooms"])


# Criar sala (somente ADMIN ou PROFESSOR da tenant)
@router.post(
    "",
    response_model=RoomResponse,
    status_code=201,
    dependencies=[Depends(require_role(UserRole.ADMIN, UserRole.PROFESSOR))],
)
async def create_room(
    tenant_id: UUID,
    body: CreateRoomRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RoomResponse:
    """
    Cadastra uma nova sala para a Tenant/Instituição.
    O campo `location` é definido por `latitude` e `longitude` (coordenadas GPS / WGS84).
    O `tolerance_radius_meters` define o raio da circunferência de presença válida.
    """
    room_repo = RoomSQLAlchemyRepository(session=db)
    tenant_repo = TenantSQLAlchemyRepository(session=db)
    use_case = CreateRoomUseCase(room_repo=room_repo, tenant_repo=tenant_repo)

    room = await use_case.execute(
        CreateRoomInput(
            tenant_id=tenant_id,
            name=body.name,
            latitude=body.latitude,
            longitude=body.longitude,
            tolerance_radius_meters=body.tolerance_radius_meters,
            created_by=current_user.id,
        )
    )
    return RoomResponse(
        id=room.id,
        tenant_id=room.tenant_id,
        created_by=room.created_by,
        name=room.name,
        latitude=room.latitude,
        longitude=room.longitude,
        tolerance_radius_meters=room.tolerance_radius_meters,
        created_at=room.created_at,
        updated_at=room.updated_at,
    )


# Listar salas da tenant
@router.get("", response_model=list[RoomResponse])
async def list_rooms(
    tenant_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> list[RoomResponse]:
    """Lista todas as salas de uma Tenant/Instituição."""
    room_repo = RoomSQLAlchemyRepository(session=db)
    tenant_repo = TenantSQLAlchemyRepository(session=db)
    use_case = ListRoomsUseCase(room_repo=room_repo, tenant_repo=tenant_repo)

    rooms = await use_case.execute(ListRoomsInput(tenant_id=tenant_id))
    return [
        RoomResponse(
            id=r.id,
            tenant_id=r.tenant_id,
            created_by=r.created_by,
            name=r.name,
            latitude=r.latitude,
            longitude=r.longitude,
            tolerance_radius_meters=r.tolerance_radius_meters,
            created_at=r.created_at,
            updated_at=r.updated_at,
        )
        for r in rooms
    ]


# Consultar sala por ID
@router.get("/{room_id}", response_model=RoomResponse)
async def get_room(
    tenant_id: UUID,
    room_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> RoomResponse:
    """Retorna os detalhes de uma sala específica."""
    room_repo = RoomSQLAlchemyRepository(session=db)
    use_case = GetRoomUseCase(room_repo=room_repo)

    room = await use_case.execute(GetRoomInput(room_id=room_id, tenant_id=tenant_id))
    return RoomResponse(
        id=room.id,
        tenant_id=room.tenant_id,
        created_by=room.created_by,
        name=room.name,
        latitude=room.latitude,
        longitude=room.longitude,
        tolerance_radius_meters=room.tolerance_radius_meters,
        created_at=room.created_at,
        updated_at=room.updated_at,
    )


# Atualizar sala (PATCH — apenas campos enviados são alterados)
@router.patch(
    "/{room_id}",
    response_model=RoomResponse,
    dependencies=[Depends(require_role(UserRole.ADMIN, UserRole.PROFESSOR))],
)
async def update_room(
    tenant_id: UUID,
    room_id: UUID,
    body: UpdateRoomRequest,
    db: AsyncSession = Depends(get_db),
) -> RoomResponse:
    """Atualiza parcialmente os dados de uma sala. Apenas os campos enviados são modificados."""
    room_repo = RoomSQLAlchemyRepository(session=db)
    use_case = UpdateRoomUseCase(room_repo=room_repo)

    room = await use_case.execute(
        UpdateRoomInput(
            room_id=room_id,
            tenant_id=tenant_id,
            name=body.name,
            latitude=body.latitude,
            longitude=body.longitude,
            tolerance_radius_meters=body.tolerance_radius_meters,
        )
    )
    return RoomResponse(
        id=room.id,
        tenant_id=room.tenant_id,
        created_by=room.created_by,
        name=room.name,
        latitude=room.latitude,
        longitude=room.longitude,
        tolerance_radius_meters=room.tolerance_radius_meters,
        created_at=room.created_at,
        updated_at=room.updated_at,
    )


# Deletar sala
@router.delete(
    "/{room_id}",
    status_code=204,
    dependencies=[Depends(require_role(UserRole.ADMIN))],
)
async def delete_room(
    tenant_id: UUID,
    room_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Remove permanentemente uma sala da Tenant. Requer papel de ADMIN."""
    room_repo = RoomSQLAlchemyRepository(session=db)
    use_case = DeleteRoomUseCase(room_repo=room_repo)

    await use_case.execute(DeleteRoomInput(room_id=room_id, tenant_id=tenant_id))
```

---

## Passo 14 — Registrar o Router em `main.py`

```python
# src/main.py
from modules.room.interface.room_router import router as room_router

app.include_router(room_router)
```

---

## Passo 15 — Testes

### Fake Repository (`tests/unit/fakes/fake_room_repository.py`)

```python
# tests/unit/fakes/fake_room_repository.py
from uuid import UUID

from modules.room.domain.entities.room import Room


class FakeRoomRepository:
    def __init__(self) -> None:
        self._rooms: dict[UUID, Room] = {}

    async def save(self, room: Room) -> Room:
        self._rooms[room.id] = room
        return room

    async def find_by_id(self, room_id: UUID) -> Room | None:
        return self._rooms.get(room_id)

    async def find_by_id_and_tenant(
        self, room_id: UUID, tenant_id: UUID
    ) -> Room | None:
        room = self._rooms.get(room_id)
        if room and room.tenant_id == tenant_id:
            return room
        return None

    async def list_by_tenant(self, tenant_id: UUID) -> list[Room]:
        return [r for r in self._rooms.values() if r.tenant_id == tenant_id]

    async def delete(self, room: Room) -> None:
        self._rooms.pop(room.id, None)
```

### Testes Unitários (`tests/unit/modules/room/`)

**Casos a cobrir em `test_room_use_cases.py`:**

```
CreateRoomUseCase:
  - [ ] Sucesso: sala criada com latitude, longitude e raio corretos
  - [ ] Erro: tenant não encontrada → ResourceNotFoundException
  - [ ] Erro: tenant deletada → ResourceNotFoundException

GetRoomUseCase:
  - [ ] Sucesso: retorna sala pelo room_id + tenant_id
  - [ ] Erro: sala não encontrada → ResourceNotFoundException
  - [ ] Erro: sala de outra tenant → ResourceNotFoundException

ListRoomsUseCase:
  - [ ] Sucesso: retorna apenas salas da tenant solicitada
  - [ ] Sucesso: retorna lista vazia quando a tenant não tem salas
  - [ ] Erro: tenant não encontrada → ResourceNotFoundException

UpdateRoomUseCase:
  - [ ] Sucesso: atualiza somente os campos fornecidos (PATCH semântico)
  - [ ] Sucesso: atualiza apenas o raio de tolerância
  - [ ] Sucesso: atualiza latitude e longitude (reposicionamento)
  - [ ] Erro: sala não encontrada → ResourceNotFoundException

DeleteRoomUseCase:
  - [ ] Sucesso: remove a sala do repositório
  - [ ] Erro: sala não encontrada → ResourceNotFoundException

Room (entidade):
  - [ ] is_within_radius retorna True quando aluno está dentro do raio
  - [ ] is_within_radius retorna False quando aluno está fora do raio
  - [ ] Casos de borda: aluno exatamente na fronteira do raio
```

### Testes de Integração (`tests/integration/modules/room/`)

**Casos a cobrir em `test_room_sqlalchemy_repository.py`:**

```
RoomSQLAlchemyRepository:
  - [ ] save() persiste a sala com localização GEOGRAPHY correta
  - [ ] find_by_id() retorna a sala com latitude/longitude corretos
  - [ ] find_by_id_and_tenant() retorna None para room de outra tenant
  - [ ] list_by_tenant() filtra corretamente por tenant_id
  - [ ] delete() remove a sala do banco
  - [ ] RoomMapper converte WKB → lat/lon e lat/lon → WKT corretamente
```

### Testes E2E (`tests/e2e/modules/room/test_room_router.py`)

```
  - [ ] POST /tenants/{id}/rooms → 201 com dados corretos
  - [ ] POST /tenants/{id}/rooms sem autenticação → 401
  - [ ] POST /tenants/{id}/rooms com role ALUNO → 403
  - [ ] POST /tenants/{id}/rooms com latitude inválida (> 90) → 422
  - [ ] POST /tenants/{id}/rooms com longitude inválida (< -180) → 422
  - [ ] GET /tenants/{id}/rooms → 200 lista as salas da tenant
  - [ ] GET /tenants/{id}/rooms/{room_id} → 200 retorna sala
  - [ ] GET /tenants/{id}/rooms/{room_id} de outra tenant → 404
  - [ ] PATCH /tenants/{id}/rooms/{room_id} → 200 atualiza parcialmente
  - [ ] DELETE /tenants/{id}/rooms/{room_id} → 204 com role ADMIN
  - [ ] DELETE /tenants/{id}/rooms/{room_id} com role PROFESSOR → 403
```

---

## Checklist de implementação

- [ ] Instalar dependência `geoalchemy2` via `uv add geoalchemy2`
- [ ] Habilitar PostGIS no banco: `CREATE EXTENSION IF NOT EXISTS postgis;`
- [ ] Criar `RoomModel` em `src/infra/database/models/room.py`
- [ ] Registrar o model em `src/infra/database/models/__init__.py`
- [ ] Gerar migration: `uv run alembic revision --autogenerate -m "create rooms table with postgis geography"`
- [ ] Verificar a migration gerada — confirmar índice GiST e extensão PostGIS
- [ ] Aplicar migration: `uv run alembic upgrade head`
- [ ] Criar estrutura de diretórios do módulo `room/`
- [ ] Criar entidade `Room` em `domain/entities/room.py`
- [ ] Criar Protocol `RoomRepository` em `domain/repositories/`
- [ ] Criar `RoomMapper` em `infra/mappers/room_mapper.py`
- [ ] Criar `RoomSQLAlchemyRepository` em `infra/repositories/`
- [ ] Criar `CreateRoomUseCase`
- [ ] Criar `GetRoomUseCase`
- [ ] Criar `ListRoomsUseCase`
- [ ] Criar `UpdateRoomUseCase`
- [ ] Criar `DeleteRoomUseCase`
- [ ] Criar schemas Pydantic em `interface/schemas/room_schemas.py`
- [ ] Criar `room_router.py` com as 5 rotas
- [ ] Registrar o router em `src/main.py`
- [ ] Criar `FakeRoomRepository` para testes unitários
- [ ] Escrever testes unitários (`test_room_use_cases.py`)
- [ ] Escrever testes de integração (`test_room_sqlalchemy_repository.py`)
- [ ] Escrever testes E2E (`test_room_router.py`)
- [ ] Executar suite completa: `uv run pytest tests/ -v`

---

## Decisões de design

| Decisão | Justificativa |
|---|---|
| `GEOGRAPHY(Point, 4326)` ao invés de dois `FLOAT` | Distâncias geodésicas precisas, índice GiST para performance, padrão da indústria (PostGIS) |
| SRID 4326 (WGS84) | Sistema de referência padrão do GPS — mesmo sistema do celular do aluno |
| `latitude`/`longitude` como `float` na entidade | Tipos nativos Python — conversão para PostGIS é responsabilidade exclusiva do mapper/infra |
| Índice GiST obrigatório | Torna `ST_DWithin` O(log n) — componente de otimização demonstrável no TCC |
| `tolerance_radius_meters` como `int` (metros) | Unidade explícita e intuitiva; evita ambiguidade com graus ou quilômetros |
| Raio entre 5m e 500m | Limites razoáveis: < 5m inviável para GPS (precisão do dispositivo); > 500m anula a validação |
| Hard delete para salas | Salas são configuração — não há necessidade de histórico. Sessões de chamada devem tratar a remoção |
| PATCH semântico no update | Evita sobrescrita acidental de coordenadas ao atualizar apenas o nome da sala |
| `ondelete="CASCADE"` tenant → room | Ao deletar a instituição, todas as salas são removidas automaticamente |
