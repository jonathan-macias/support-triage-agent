"""Punto de entrada de la API.

Arrancar en modo desarrollo (se recarga al guardar cambios):
    uv run fastapi dev app/main.py
Documentación interactiva: http://127.0.0.1:8000/docs
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import settings
from app.database import create_db_and_tables
from app.routers import tickets


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Código ANTES del yield: se ejecuta una vez al arrancar el servidor.
    create_db_and_tables()
    yield
    # Código DESPUÉS del yield: se ejecutaría al apagar (cerrar conexiones, etc.).


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)

app.include_router(tickets.router)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}
