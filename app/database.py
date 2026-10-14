"""Conexión a la base de datos.

- `engine`: el objeto que sabe cómo conectarse a PostgreSQL (mantiene un pool
  de conexiones). Se crea una sola vez al arrancar.
- `get_session`: una *dependencia* de FastAPI. Cada petición HTTP recibe su
  propia `Session` (una "conversación" con la BD) y se cierra al terminar.
"""

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends
from sqlmodel import Session, SQLModel, create_engine

from app.config import settings

engine = create_engine(settings.database_url)


def create_db_and_tables() -> None:
    # Importar los modelos los "registra" en SQLModel.metadata;
    # sin este import, create_all no sabría qué tablas crear.
    from app import models  # noqa: F401

    SQLModel.metadata.create_all(engine)


def get_session() -> Iterator[Session]:
    # `yield` convierte esta función en un generador: FastAPI ejecuta el código
    # hasta el yield, entrega la sesión al endpoint y, cuando la respuesta
    # termina, continúa y sale del `with` (cerrando la sesión).
    with Session(engine) as session:
        yield session


# Atajo reutilizable. En un endpoint, `session: SessionDep` significa
# "FastAPI, llama a get_session() y pásame el resultado".
SessionDep = Annotated[Session, Depends(get_session)]
