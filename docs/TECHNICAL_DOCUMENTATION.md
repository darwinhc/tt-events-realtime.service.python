# Technical Documentation

Events Service is a small realtime backend for managing events, locations, and event participants. The project is organized around a domain-first architecture: domain rules live in `src/domain`, infrastructure lives in `src/infra`, and FastAPI/job entrypoints live in `src/entrypoints`.

The main design goal is to keep business behavior testable without coupling it to FastAPI, SQLAlchemy, or WebSocket transport details.

## High-level architecture

```mermaid
flowchart TB
    subgraph Delivery[Delivery layer]
        UserAPI[User FastAPI app\nHTTP + WebSocket]
        InternalAPI[Internal FastAPI app]
        Jobs[Scheduled jobs]
    end

    subgraph Application[Composition root]
        Builder[src/application.py]
        AppModel[Application object\nuse-case callables + adapters]
    end

    subgraph Domain[Domain layer]
        Entities[Entities and DTOs]
        UseCases[Use cases]
        Ports[Ports / Protocols]
    end

    subgraph Infra[Infrastructure adapters]
        Auth[SimpleNameAuthentication]
        SQLA[SQLAlchemy repositories]
        Publisher[FastAPIWebSocketPublisher]
        Logging[Logging context]
    end

    DB[(SQLite / PostgreSQL)]

    UserAPI --> AppModel
    InternalAPI --> AppModel
    Jobs --> AppModel
    Builder --> AppModel
    AppModel --> UseCases
    UseCases --> Entities
    UseCases --> Ports
    Ports --> Auth
    Ports --> SQLA
    Ports --> Publisher
    SQLA --> DB
    UserAPI --> Logging
    Jobs --> Logging
```

## Layer responsibilities

| Layer | Main responsibility |
|---|---|
| `src/domain/entities` | Validated domain models such as `Event`, `Location`, `Joiner`, `User`, and `RealtimeEvent`. |
| `src/domain/dtos` | Input and query objects such as event creation, event updates, filters, and pagination. |
| `src/domain/use_cases` | Business workflows: create event, join event, cancel event, update location, cleanup old records. |
| `src/domain/ports` | Interfaces expected by the domain: repositories, authentication, realtime publisher. |
| `src/infra` | Concrete adapters for SQLAlchemy, authentication, logging, and WebSocket publishing. |
| `src/entrypoints` | FastAPI apps and command-line job entrypoints. |
| `src/application.py` | Composition root. It wires use cases with concrete adapters. |

## Request lifecycle

```mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant API as FastAPI route
    participant APP as Application object
    participant UC as Domain use case
    participant Repo as SQLAlchemy repository
    participant DB as Database
    participant WS as WebSocket publisher

    C->>API: HTTP request
    API->>APP: Call composed use case
    APP->>UC: Execute domain workflow
    UC->>Repo: Read/write through port
    Repo->>DB: SQLAlchemy transaction
    DB-->>Repo: Persisted model
    Repo-->>UC: Domain entity
    UC->>WS: Publish realtime event when needed
    UC-->>APP: Result
    APP-->>API: Domain DTO/entity
    API-->>C: JSON response + X-Transaction-ID
```

The HTTP API remains the source of truth. WebSocket events are notifications, not a replacement for reading current state from HTTP endpoints.

## Domain behavior

The service models three central operations:

1. **Events** are created by an organizer, linked to a location, optionally scheduled, and can be active or canceled.
2. **Locations** are flexible. An event can reference an existing location or create an inline location during event creation.
3. **Joiners** represent active or historical participation. A user can only have one active join record for the same event.

Important rules are enforced in the domain and persistence layers:

- Event title must be valid and non-empty.
- Duration must be positive.
- Only the organizer can update, cancel, or restore an event.
- Canceled or completed events cannot be joined.
- Duplicate active joins are rejected.
- Leaving an event sets `left_at` instead of deleting the joiner row.
- Location coordinates must be complete when provided.

## Database model

```mermaid
erDiagram
    USERS ||--o{ EVENTS : organizes
    USERS ||--o{ JOINERS : joins
    LOCATIONS ||--o{ EVENTS : hosts
    EVENTS ||--o{ JOINERS : has

    USERS {
        int id PK
        text name
    }

    LOCATIONS {
        int id PK
        text name
        text address
        text country
        text city
        text postal_code
        real latitude
        real longitude
        datetime created_at
    }

    EVENTS {
        int id PK
        text title
        int organizer_id FK
        datetime scheduled_at
        int duration_in_minutes
        text status
        datetime canceled_at
        datetime deletion_scheduled_at
        int location_id FK
    }

    JOINERS {
        int id PK
        int user_id FK
        int event_id FK
        datetime joined_at
        datetime left_at
    }
```

The database schema is managed by Alembic. Runtime startup does not call `Base.metadata.create_all()`. This keeps application startup separate from schema evolution.

Typical setup:

```bash
alembic upgrade head
uvicorn src.entrypoints.fastapi.wsgi:app --reload
```

## Migrations and PostgreSQL

Local development can use SQLite. The hosted deployment uses Supabase PostgreSQL with a URL such as:

```text
postgresql+psycopg://user:password@host:5432/database
```

Alembic reads the database URL from `EVENTS_DATABASE_URL` or from `-x database_url=...` when migrations are executed programmatically in tests.

```bash
alembic upgrade head
alembic downgrade -1
alembic revision --autogenerate -m "describe change"
```

## Single-instance operations

This service is designed for a single fixed instance:

```mermaid
flowchart LR
    Dev[Developer / CI]
    Migration[Alembic migration step]
    Render[Render web service\n1 instance / 1 worker]
    Supabase[(Supabase PostgreSQL)]
    Client[Browser client]

    Dev --> Migration
    Migration --> Supabase
    Client -->|HTTP + WebSocket| Render
    Render --> Supabase
```

Operational expectations:

- Run migrations before starting the service.
- Run one application instance.
- Run one worker process.
- Do not enable horizontal autoscaling without replacing the realtime publisher.
- Keep the internal API and cleanup jobs separate from the public user API.

This constraint is intentional. The current in-memory WebSocket publisher is simple and predictable for one instance, but it is not a distributed event bus.

## Observability

The FastAPI app propagates request context using `X-Transaction-ID`.

For HTTP requests, the service logs:

- transaction ID;
- HTTP method;
- route and path;
- status code;
- client IP;
- duration in milliseconds.

For WebSocket connections, the service logs connection and disconnection events with the same transaction ID concept.

## Testing strategy

The tests cover domain behavior, persistence adapters, FastAPI routes, WebSocket broadcasting, logging context, settings, custom SQLAlchemy types, and Alembic-backed integration setup.

Run:

```bash
pytest
pylint src tests
radon cc src -s -a
```

Current result for this version:

```text
109 passed
Total coverage: 86.38%
```

## Design trade-offs

| Decision | Reason | Trade-off |
|---|---|---|
| Domain-first structure | Keeps business logic testable and independent from frameworks. | More files than a simple CRUD script. |
| Simple bearer-name authentication | Enough for the assignment scope and easy to replace behind a port. | Not production-grade authentication. |
| In-memory WebSocket publisher | Simple, fast, and aligned with one Render instance. | Not compatible with multi-instance fan-out. |
| Alembic-managed schema | Startup and schema evolution are separated. | Deployment needs an explicit migration step. |
| HTTP as source of truth | Frontend can always reconcile state after missed WebSocket messages. | Client must handle reconnection intentionally. |
