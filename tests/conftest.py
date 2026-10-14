"""Fixtures compartidas por todos los tests.

Una *fixture* de pytest es una función que prepara algo que los tests piden
por nombre: `def test_x(client): ...` recibe lo que devuelve `client()`.

Los tests NO usan PostgreSQL: usan SQLite en memoria (rápido, sin Docker).
Lo conseguimos con `app.dependency_overrides`, que le dice a FastAPI
"cuando un endpoint pida get_session, usa esta otra sesión".
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.database import get_session
from app.main import app


@pytest.fixture
def session() -> Iterator[Session]:
    # StaticPool + check_same_thread=False: todas las conexiones comparten la
    # misma BD en memoria (si no, cada conexión vería una BD vacía distinta).
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture
def client(session: Session) -> Iterator[TestClient]:
    app.dependency_overrides[get_session] = lambda: session
    # Sin `with TestClient(app)`, el lifespan no se ejecuta, así que no se
    # intenta conectar a PostgreSQL durante los tests.
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def ticket_payload() -> dict[str, str]:
    return {
        "subject": "No puedo iniciar sesión",
        "body": "Me sale 'contraseña incorrecta' aunque la acabo de cambiar.",
        "customer_email": "ana@example.com",
    }
