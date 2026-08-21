Sim. Vou preservar **a mesma filosofia arquitetural do seu documento NestJS**, mas adaptando o que é específico do Nest para o ecossistema **FastAPI + SQLAlchemy 2.0 + Alembic + Pydantic**.

A principal mudança é: **não vamos tentar transformar FastAPI em NestJS**. Vamos manter Clean Architecture, Ports & Adapters, módulos por domínio e Dependency Inversion, usando os mecanismos naturais do Python/FastAPI.

---

# Backend Architecture — Context

## Stack

**FastAPI · Python 3.12 · SQLAlchemy 2.0 · PostgreSQL · Alembic · Redis · Celery · Pydantic · Resend**

Deploy:

**Railway / Docker · PostgreSQL · Redis**

---

# Core Principle — Clean Architecture

Dependencies point **inward only**.

```text
interface → application → domain ← (never outward)
                              ↑
                            infra
```

- `domain/` has zero knowledge of FastAPI, SQLAlchemy, PostgreSQL, HTTP, Redis or any external tool
- `application/` orchestrates use cases and depends only on domain abstractions
- `infra/` implements interfaces/ports defined by the domain
- `interface/` handles HTTP and translates external requests into application inputs
- Dependency Injection is handled through FastAPI dependencies and explicit composition
- Repository abstractions are defined in the domain using `Protocol` or abstract classes

The architecture must not depend on the framework.

---

# Multi-Tenant Rule

Every query **must filter by `tenant_id`**. No exceptions.

Tenant is resolved from:

```text
subdomain → JWT claim → API Key
```

in that priority order.

The tenant resolution process is separated from the business logic.

Conceptually:

```text
HTTP Request
      ↓
Tenant Middleware / Dependency
      ↓
Tenant Context
      ↓
Authentication
      ↓
Router
      ↓
Use Case
      ↓
Repository
      ↓
Database
```

Every repository method that accesses tenant-owned data must receive `tenant_id` explicitly:

```python
async def find_by_id(
    self,
    appointment_id: str,
    tenant_id: str,
) -> Appointment | None:
    ...
```

```python
async def find_many(
    self,
    filters: AppointmentFilters,
    tenant_id: str,
) -> list[Appointment]:
    ...
```

The repository implementation must always apply the tenant filter.

```python
stmt = (
    select(AppointmentModel)
    .where(
        AppointmentModel.id == appointment_id,
        AppointmentModel.tenant_id == tenant_id,
    )
)
```

---

# Folder Structure

```text
app/
├── main.py
│
├── shared/
│   ├── value_objects/
│   │   ├── reservation_token.py
│   │   ├── time_slot.py
│   │   ├── email.py
│   │   └── phone.py
│   │
│   └── enums/
│       ├── appointment_status.py
│       ├── user_role.py
│       ├── notification_channel.py
│       └── day_of_week.py
│
├── config/
│   ├── settings.py
│   ├── database.py
│   ├── redis.py
│   └── mail.py
│
├── infra/
│   ├── database/
│   │   ├── session.py
│   │   └── base.py
│   │
│   ├── mail/
│   │   ├── mail_service.py
│   │   └── templates/
│   │       ├── booking_confirmed.py
│   │       ├── booking_cancelled.py
│   │       └── booking_reminder.py
│   │
│   ├── queue/
│   │   ├── celery_app.py
│   │   └── workers/
│   │       ├── email_worker.py
│   │       └── reminder_worker.py
│   │
│   └── redis/
│       └── redis_client.py
│
├── security/
│   ├── dependencies/
│   │   ├── current_user.py
│   │   ├── current_tenant.py
│   │   └── auth.py
│   │
│   ├── jwt.py
│   └── password.py
│
└── modules/
    │
    ├── appointment/
    │   ├── domain/
    │   │   ├── entities/
    │   │   │   └── appointment.py
    │   │   │
    │   │   ├── repositories/
    │   │   │   └── appointment_repository.py
    │   │   │
    │   │   └── services/
    │   │       ├── conflict_checker.py
    │   │       ├── availability.py
    │   │       └── buffer_calculator.py
    │   │
    │   ├── application/
    │   │   └── use_cases/
    │   │       ├── create_appointment.py
    │   │       ├── cancel_appointment.py
    │   │       ├── reschedule_appointment.py
    │   │       └── get_availability.py
    │   │
    │   ├── infra/
    │   │   ├── repositories/
    │   │   │   └── appointment_sqlalchemy_repository.py
    │   │   │
    │   │   └── mappers/
    │   │       └── appointment_mapper.py
    │   │
    │   └── interface/
    │       ├── router.py
    │       └── schemas/
    │           ├── create_appointment.py
    │           ├── cancel_appointment.py
    │           └── reschedule_appointment.py
    │
    ├── schedule/
    │   ├── domain/
    │   │   ├── entities/
    │   │   ├── repositories/
    │   │   └── services/
    │   │
    │   ├── application/
    │   │   └── use_cases/
    │   │
    │   ├── infra/
    │   │   ├── repositories/
    │   │   └── mappers/
    │   │
    │   └── interface/
    │       ├── router.py
    │       └── schemas/
    │
    ├── resource/
    │   ├── domain/
    │   │   ├── entities/
    │   │   └── repositories/
    │   │
    │   ├── application/
    │   │   └── use_cases/
    │   │
    │   ├── infra/
    │   │   ├── repositories/
    │   │   └── mappers/
    │   │
    │   └── interface/
    │       ├── router.py
    │       └── schemas/
    │
    ├── service/
    │   ├── domain/
    │   │   ├── entities/
    │   │   └── repositories/
    │   │
    │   ├── application/
    │   │   └── use_cases/
    │   │
    │   ├── infra/
    │   │   ├── repositories/
    │   │   └── mappers/
    │   │
    │   └── interface/
    │       ├── router.py
    │       └── schemas/
    │
    ├── customer/
    │   ├── domain/
    │   │   ├── entities/
    │   │   └── repositories/
    │   │
    │   ├── application/
    │   │   └── use_cases/
    │   │
    │   ├── infra/
    │   │   ├── repositories/
    │   │   └── mappers/
    │   │
    │   └── interface/
    │       ├── router.py
    │       └── schemas/
    │
    ├── tenant/
    │   ├── domain/
    │   │   ├── entities/
    │   │   └── repositories/
    │   │
    │   ├── application/
    │   │   └── use_cases/
    │   │
    │   ├── infra/
    │   │   ├── repositories/
    │   │   └── mappers/
    │   │
    │   └── interface/
    │       ├── router.py
    │       └── schemas/
    │
    ├── user/
    │   ├── domain/
    │   │   ├── entities/
    │   │   └── repositories/
    │   │
    │   ├── application/
    │   │   └── use_cases/
    │   │
    │   ├── infra/
    │   │   ├── repositories/
    │   │   └── mappers/
    │   │
    │   └── interface/
    │       ├── router.py
    │       └── schemas/
    │
    ├── auth/
    │   ├── application/
    │   │   └── use_cases/
    │   │       ├── login.py
    │   │       └── refresh_token.py
    │   │
    │   ├── infra/
    │   │   └── jwt_service.py
    │   │
    │   └── interface/
    │       ├── router.py
    │       └── schemas/
    │
    └── widget/
        ├── application/
        │   └── use_cases/
        │       ├── get_public_tenant.py
        │       ├── get_public_services.py
        │       ├── get_public_availability.py
        │       ├── get_public_appointment.py
        │       ├── create_public_appointment.py
        │       └── cancel_public_appointment.py
        │
        └── interface/
            ├── router.py
            └── schemas/

alembic/
├── versions/
├── env.py
└── script.py.mako

tests/
├── unit/
├── integration/
└── e2e/

pyproject.toml
uv.lock
```

---

# Layer Responsibilities

## `shared/`

Value objects and enums shared across multiple modules.

If only one module uses something, it stays inside that module's `domain/`.

### `value_objects/`

Immutable domain concepts with validation.

Examples:

```text
ReservationToken
TimeSlot
Email
Phone
```

### `enums/`

Domain-level enumerations:

```text
AppointmentStatus
UserRole
NotificationChannel
DayOfWeek
```

---

# `modules/[name]/domain/`

The domain contains the **core business rules**.

It must not import:

```text
FastAPI
SQLAlchemy
Pydantic
Redis
Celery
PostgreSQL
HTTP
```

For example:

```text
appointment/
└── domain/
    ├── entities/
    │   └── appointment.py
    │
    ├── repositories/
    │   └── appointment_repository.py
    │
    └── services/
        ├── conflict_checker.py
        ├── availability.py
        └── buffer_calculator.py
```

### Entities

Represent domain objects and their business behavior.

```python
class Appointment:
    ...
```

The entity is **not** a SQLAlchemy model.

---

## Repository Interface

The domain defines what it needs from persistence.

Using Python's `Protocol`:

```python
from typing import Protocol


class AppointmentRepository(Protocol):

    async def find_by_id(
        self,
        appointment_id: str,
        tenant_id: str,
    ) -> Appointment | None:
        ...

    async def save(
        self,
        appointment: Appointment,
    ) -> Appointment:
        ...
```

The domain knows **what** it needs, not **how** it is implemented.

---

# `modules/[name]/application/`

Contains application use cases.

A use case:

- receives plain input
- orchestrates domain logic
- calls repository interfaces
- returns plain output
- does not know HTTP
- does not know SQLAlchemy
- does not know FastAPI

Example:

```python
class CreateAppointmentUseCase:

    def __init__(
        self,
        repository: AppointmentRepository,
    ):
        self.repository = repository

    async def execute(self, data):
        ...
```

One use case per operation:

```text
create_appointment.py
cancel_appointment.py
reschedule_appointment.py
get_availability.py
```

---

# `modules/[name]/infra/`

Contains concrete implementations of external dependencies.

For example:

```text
appointment/
└── infra/
    ├── repositories/
    │   └── appointment_sqlalchemy_repository.py
    │
    └── mappers/
        └── appointment_mapper.py
```

The repository implementation uses SQLAlchemy:

```python
class AppointmentSQLAlchemyRepository:

    def __init__(self, session):
        self.session = session

    async def find_by_id(
        self,
        appointment_id: str,
        tenant_id: str,
    ):
        ...
```

The dependency direction remains:

```text
Domain
   ↑
   │ implements
   │
Infrastructure
```

---

# `modules/[name]/interface/`

This is the external boundary of the application.

In FastAPI, this is primarily:

```text
router.py
schemas/
```

### `router.py`

Equivalent conceptually to a NestJS controller.

Example:

```python
router = APIRouter(
    prefix="/appointments",
    tags=["Appointments"],
)
```

The router should be thin:

```python
@router.post("/")
async def create_appointment(
    data: CreateAppointmentRequest,
    use_case: CreateAppointmentUseCase = Depends(
        get_create_appointment_use_case
    ),
):
    return await use_case.execute(data)
```

The router **does not contain business logic**.

---

# Pydantic Schemas

Pydantic replaces the role your NestJS DTOs played.

```python
from pydantic import BaseModel
from datetime import datetime


class CreateAppointmentRequest(BaseModel):
    customer_id: str
    starts_at: datetime
    ends_at: datetime
```

Pydantic is responsible for validating external input.

The important distinction is:

```text
Pydantic Schema
      ↓
HTTP boundary
```

It should not become your domain entity.

---

# `config/`

All environment configuration lives here.

Instead of:

```python
os.getenv("DATABASE_URL")
```

being scattered throughout the application, centralize it.

For example:

```python
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    redis_url: str
    jwt_secret: str

    class Config:
        env_file = ".env"
```

Then the rest of the application receives configuration through dependency injection.

Rule:

> No business code reads environment variables directly.

---

# `infra/database/`

Contains SQLAlchemy infrastructure.

```text
infra/
└── database/
    ├── session.py
    └── base.py
```

Responsibilities include:

- SQLAlchemy engine
- async session factory
- database connection
- declarative base
- transaction management

For example:

```text
AsyncEngine
     ↓
async_sessionmaker
     ↓
AsyncSession
```

---

# SQLAlchemy Models

SQLAlchemy models represent the persistence model.

They are **not domain entities**.

For example:

```text
Domain:

Appointment
```

versus:

```text
Infrastructure:

AppointmentModel
```

The mapper converts between them:

```text
AppointmentModel
       ↓
AppointmentMapper
       ↓
Appointment
```

And the reverse:

```text
Appointment
       ↓
AppointmentMapper
       ↓
AppointmentModel
```

This keeps your domain independent from SQLAlchemy.

---

# Alembic

Alembic is responsible for database migrations.

The architecture becomes:

```text
SQLAlchemy
    │
    │ defines persistence models
    ▼
Alembic
    │
    │ creates/applies migrations
    ▼
PostgreSQL
```

Migration files live in:

```text
alembic/
└── versions/
```

Example:

```text
001_create_tenants.py
002_create_users.py
003_create_appointments.py
```

Alembic replaces the role that **Prisma Migrate** played in your NestJS project.

---

# `security/`

Cross-cutting authentication and authorization concerns.

```text
security/
├── dependencies/
│   ├── current_user.py
│   ├── current_tenant.py
│   └── auth.py
│
├── jwt.py
└── password.py
```

FastAPI does not have NestJS-style Guards.

Instead, authentication/authorization is commonly expressed through **Dependencies**.

Conceptually:

```text
NestJS

JwtGuard
TenantGuard
RolesGuard
```

becomes:

```text
FastAPI

get_current_user()
get_current_tenant()
require_role()
```

used with:

```python
Depends(...)
```

---

# Dependency Injection

FastAPI's Dependency Injection system is based around `Depends`.

Example:

```python
def get_appointment_repository(
    session: AsyncSession = Depends(get_db),
):
    return AppointmentSQLAlchemyRepository(session)
```

Then:

```python
@router.post("/")
async def create_appointment(
    data: CreateAppointmentRequest,
    repository: AppointmentRepository = Depends(
        get_appointment_repository
    ),
):
    ...
```

The important rule remains:

> Infrastructure implementations are composed at the application boundary, not inside the domain.

---

# Request Lifecycle

The equivalent lifecycle becomes:

```text
HTTP Request
      ↓
Middleware
      ↓
Tenant Resolution
      ↓
Authentication Dependency
      ↓
Authorization Dependency
      ↓
FastAPI Router
      ↓
Pydantic Validation
      ↓
Use Case
      ↓
Domain Service
      ↓
Repository Interface
      ↓
SQLAlchemy Repository
      ↓
PostgreSQL
      ↓
Mapper
      ↓
HTTP Response
```

For asynchronous operations:

```text
HTTP Request
      ↓
Use Case
      ↓
Celery Task
      ↓
Redis
      ↓
Worker
      ↓
External Service
```

---

# Async Processing

Heavy operations must not block the request lifecycle.

Examples:

```text
Email
Reminder
Webhook
Report generation
Bulk notification
```

Use:

```text
FastAPI
   ↓
Celery
   ↓
Redis
   ↓
Worker
```

For example:

```python
send_booking_confirmation.delay(
    appointment_id
)
```

The API returns without waiting for the email provider.

---

# Naming Conventions

| Type                      | Pattern                      | Example                                |
| ------------------------- | ---------------------------- | -------------------------------------- |
| Entity                    | `snake_case.py`              | `appointment.py`                       |
| Value Object              | `snake_case.py`              | `reservation_token.py`                 |
| Repository Interface      | `*_repository.py`            | `appointment_repository.py`            |
| Repository Implementation | `*_sqlalchemy_repository.py` | `appointment_sqlalchemy_repository.py` |
| Use Case                  | `verb_name.py`               | `create_appointment.py`                |
| Domain Service            | `snake_case.py`              | `conflict_checker.py`                  |
| Router                    | `router.py`                  | `router.py`                            |
| Request Schema            | `snake_case.py`              | `create_appointment.py`                |
| Mapper                    | `*_mapper.py`                | `appointment_mapper.py`                |
| Enum                      | `snake_case.py`              | `appointment_status.py`                |
| Celery Worker             | `*_worker.py`                | `email_worker.py`                      |

---

# Non-Negotiable Rules

### 1. Domain never imports infrastructure

```text
domain ❌→ SQLAlchemy
domain ❌→ FastAPI
domain ❌→ Pydantic
domain ❌→ Redis
domain ❌→ Celery
```

---

### 2. Use Cases never access SQLAlchemy directly

❌:

```python
class CreateAppointmentUseCase:

    async def execute(self):
        await session.execute(...)
```

✅:

```python
class CreateAppointmentUseCase:

    def __init__(
        self,
        repository: AppointmentRepository,
    ):
        self.repository = repository
```

---

### 3. Routers never contain business logic

❌:

```python
@router.post("/")
async def create(...):

    if appointment.starts_at < ...:
        ...

    if conflicting:
        ...

    await session.execute(...)
```

✅:

```python
@router.post("/")
async def create(
    data: CreateAppointmentRequest,
    use_case: CreateAppointmentUseCase = Depends(...),
):
    return await use_case.execute(data)
```

---

### 4. Every tenant-owned query must include `tenant_id`

```python
.where(
    AppointmentModel.id == appointment_id,
    AppointmentModel.tenant_id == tenant_id,
)
```

No exceptions.

---

### 5. Environment variables are centralized

Only:

```text
config/
```

can access environment variables.

Business logic receives configuration through dependencies.

---

### 6. Heavy operations use Celery

Email, reminders, reports and webhooks should not block the HTTP request.

```text
FastAPI → Celery → Redis → Worker
```

---

### 7. Domain entities are never returned directly from HTTP

Use a mapper/schema:

```text
Domain Entity
     ↓
Response Schema
     ↓
FastAPI
```

---

### 8. Repository interfaces belong to the domain

```text
domain/
└── repositories/
    └── appointment_repository.py
```

Implementations belong to infrastructure:

```text
infra/
└── repositories/
    └── appointment_sqlalchemy_repository.py
```

---

### 9. Shared concepts belong in `shared/`

If a value object or enum is used by only one module:

```text
appointment/domain/
```

If used by several modules:

```text
shared/
```

---

### 10. Each module is self-contained

Each business module owns its:

```text
domain/
application/
infra/
interface/
```

For example:

```text
appointment/
├── domain/
├── application/
├── infra/
└── interface/
```

This prevents the application from becoming one enormous global `services/` or `repositories/` folder.

---

# Final Architecture

The complete dependency flow is:

```text
                    ┌─────────────────────┐
                    │       FastAPI       │
                    │     Interface      │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │     Application     │
                    │     Use Cases       │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │       Domain        │
                    │ Entities / Services │
                    │   Repository Ports  │
                    └──────────┬──────────┘
                               ▲
                               │ implements
                    ┌──────────┴──────────┐
                    │   Infrastructure    │
                    │    SQLAlchemy       │
                    │ Redis / Celery      │
                    │ Mail / External APIs│
                    └─────────────────────┘
```

E a infraestrutura:

```text
                         FastAPI
                            │
             ┌──────────────┼──────────────┐
             ▼              ▼              ▼
         PostgreSQL       Redis          Storage
             ▲              ▲
             │              │
        SQLAlchemy        Celery
             │              │
             └───────┬──────┘
                     │
                  Workers
```

### Stack final

```text
Python 3.12
    │
    ├── FastAPI
    ├── Pydantic
    ├── SQLAlchemy 2.0
    ├── GeoAlchemy2
    ├── Alembic
    ├── Celery
    ├── Redis
    ├── PyJWT
    └── Pytest

Infrastructure
    │
    ├── PostgreSQL + PostGIS
    ├── Redis
    └── Docker
```
