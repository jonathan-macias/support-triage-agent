# Support Triage Agent

AI agent that triages customer support tickets with tool calling and an MCP server over a Python (FastAPI) backend, Pydantic AI, evals in CI.

> Estado: **Fase 2**: API REST de tickets (FastAPI + PostgreSQL) y agente de triage con Pydantic AI + Gemini. El servidor MCP y las evals llegan en las siguientes fases.

## Requisitos

- Python 3.12 y [uv](https://docs.astral.sh/uv/)
- Docker Desktop (para PostgreSQL)
- Una API key de Gemini: https://aistudio.google.com/apikey

## Arrancar en local

```bash
uv sync                                    # instala dependencias en .venv
docker compose up -d                       # PostgreSQL en localhost:5433
cp .env.example .env                       # configuración local → pega tu GOOGLE_API_KEY
uv run python -m scripts.seed              # (opcional) carga tickets de ejemplo
uv run python -m fastapi dev app/main.py   # API en http://127.0.0.1:8000
```

Documentación interactiva: http://127.0.0.1:8000/docs

> **Windows con Smart App Control:** bloquea los lanzadores `.exe` de `.venv\Scripts` (`fastapi.exe`, `pytest.exe`). Por eso se usan como módulos: `uv run python -m fastapi ...`, `uv run python -m pytest`.

## Tests

```bash
uv run python -m pytest
```

Los tests usan SQLite en memoria y modelos de IA falsos (`TestModel` / `FunctionModel`): no necesitan Docker, ni API key, ni hacen llamadas con coste.

## El agente de triage

`POST /tickets/{id}/triage` ejecuta el agente sobre un ticket:

1. Recibe el ticket y unas instrucciones con los criterios de prioridad y categoría.
2. Decide qué **tools** usar: `get_customer_history` (tickets anteriores del cliente) y `search_similar_tickets` (detectar incidencias masivas).
3. Devuelve una salida estructurada y validada (`priority`, `category`, `summary`, `suggested_reply`) que se guarda en el ticket.

El modelo se configura con `AI_MODEL` en `.env` (por defecto `google:gemini-3.5-flash-lite`).

## Estructura

```
app/
├── main.py              # crea la app FastAPI y registra los routers
├── config.py            # configuración leída de .env
├── database.py          # conexión a PostgreSQL y dependencia get_session
├── models.py            # tablas de la base de datos (Ticket)
├── schemas.py           # lo que la API recibe y devuelve (Pydantic)
├── agent/triage.py      # agente Pydantic AI: instrucciones, tools, salida estructurada
├── services/tickets.py  # lógica de negocio (reutilizable por el agente y MCP)
├── services/triage.py   # ejecuta el agente y guarda el resultado
└── routers/tickets.py   # endpoints HTTP /tickets
scripts/seed.py          # tickets de ejemplo
tests/                   # tests con pytest
```

## Endpoints

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/health` | Estado de la API |
| POST | `/tickets` | Crear ticket |
| GET | `/tickets` | Listar (filtros: `status`, `priority`, `category`, `customer_email`; paginación: `limit`, `offset`) |
| GET | `/tickets/{id}` | Obtener un ticket |
| PATCH | `/tickets/{id}` | Actualizar parcialmente |
| DELETE | `/tickets/{id}` | Borrar |
| POST | `/tickets/{id}/triage` | Triage con el agente de IA |
