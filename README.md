# Support Triage Agent

AI agent that triages customer support tickets with tool calling and an MCP server over a Python (FastAPI) backend, Pydantic AI, evals in CI.

> Estado: **Fase 1** — API REST de tickets (FastAPI + PostgreSQL). El agente, el servidor MCP y las evals llegan en las siguientes fases.

## Requisitos

- Python 3.12 y [uv](https://docs.astral.sh/uv/)
- Docker Desktop (para PostgreSQL)

## Arrancar en local

```bash
uv sync                          # instala dependencias en .venv
docker compose up -d             # PostgreSQL en localhost:5433
cp .env.example .env             # configuración local
uv run fastapi dev app/main.py   # API en http://127.0.0.1:8000
```

Documentación interactiva: http://127.0.0.1:8000/docs

## Tests

```bash
uv run pytest
```

Los tests usan SQLite en memoria, no necesitan Docker.

## Estructura

```
app/
├── main.py              # crea la app FastAPI y registra los routers
├── config.py            # configuración leída de .env
├── database.py          # conexión a PostgreSQL y dependencia get_session
├── models.py            # tablas de la base de datos (Ticket)
├── schemas.py           # lo que la API recibe y devuelve (Pydantic)
├── services/tickets.py  # lógica de negocio (reutilizable por el agente y MCP)
└── routers/tickets.py   # endpoints HTTP /tickets
tests/                   # tests con pytest
```

## Endpoints

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/health` | Estado de la API |
| POST | `/tickets` | Crear ticket |
| GET | `/tickets` | Listar (filtros: `status`, `priority`, `category`; paginación: `limit`, `offset`) |
| GET | `/tickets/{id}` | Obtener un ticket |
| PATCH | `/tickets/{id}` | Actualizar parcialmente |
| DELETE | `/tickets/{id}` | Borrar |
