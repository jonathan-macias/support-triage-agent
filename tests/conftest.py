"""Tests run against in-memory SQLite (no Docker) and never call a real LLM."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from pydantic_ai import models
from sqlalchemy import Engine
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.database import get_session
from app.main import app

# Fail loudly instead of sending a real (billable) request to a model provider.
models.ALLOW_MODEL_REQUESTS = False


@pytest.fixture
def engine() -> Engine:
    # StaticPool keeps a single connection so every session sees the same in-memory DB.
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    with Session(engine) as session:
        yield session


@pytest.fixture
def client(session: Session) -> Iterator[TestClient]:
    app.dependency_overrides[get_session] = lambda: session
    # Not used as a context manager, so the lifespan (which connects to PostgreSQL) never runs.
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def ticket_payload() -> dict[str, str]:
    return {
        "subject": "I can't log in",
        "body": "I get 'wrong password' even though I just reset it.",
        "customer_email": "ana@example.com",
    }
