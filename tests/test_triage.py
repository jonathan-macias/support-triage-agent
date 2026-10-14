"""Tests del agente de triage.

Nunca llaman a Gemini: `triage_agent.override(model=...)` sustituye el modelo
real por uno falso que controlamos.
- TestModel: llama a todas las tools y genera una salida válida "de relleno".
- FunctionModel: nosotros escribimos lo que "responde el modelo" en cada paso.
"""

import threading
import time
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from pydantic_ai import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import ToolReturnPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.test import TestModel
from sqlmodel import Session

from app.agent.triage import triage_agent
from app.config import settings
from app.schemas import TicketCreate
from app.services import tickets as ticket_service


@pytest.fixture
def fake_api_key(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    # build_model() exige una key; con override el modelo real nunca se usa
    monkeypatch.setattr(settings, "google_api_key", "test-key")
    yield


def scripted_model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    """Simula un modelo que primero consulta el historial y luego responde."""
    tool_returns = [
        part for message in messages for part in message.parts if isinstance(part, ToolReturnPart)
    ]
    if not tool_returns:
        # Paso 1: el "modelo" pide ejecutar una tool
        return ModelResponse(parts=[ToolCallPart("get_customer_history", {})])

    # Paso 2: ya tiene el historial → entrega la salida final (tool "final_result")
    history = tool_returns[0].content
    priority = "high" if history else "medium"
    return ModelResponse(
        parts=[
            ToolCallPart(
                "final_result",
                {
                    "priority": priority,
                    "category": "billing",
                    "summary": "Cliente reclama de nuevo un error en su factura.",
                    "suggested_reply": "Hola, sentimos las molestias. Lo revisamos hoy mismo.",
                },
            )
        ]
    )


def test_triage_saves_agent_result(
    client: TestClient, session: Session, fake_api_key: None
) -> None:
    email = "marta@example.com"
    ticket_service.create_ticket(
        session, TicketCreate(subject="Factura mal", body="Importe incorrecto", customer_email=email)
    )
    current = ticket_service.create_ticket(
        session, TicketCreate(subject="Sigo esperando", body="Nadie responde", customer_email=email)
    )

    with triage_agent.override(model=FunctionModel(scripted_model)):
        response = client.post(f"/tickets/{current.id}/triage")

    assert response.status_code == 200
    data = response.json()
    # "high" porque la tool encontró un ticket previo del mismo cliente
    assert data["priority"] == "high"
    assert data["category"] == "billing"
    assert data["summary"].startswith("Cliente reclama")
    assert data["suggested_reply"]
    # Y quedó guardado en la base de datos
    assert client.get(f"/tickets/{current.id}").json()["priority"] == "high"


def test_tools_never_run_concurrently(
    client: TestClient,
    ticket_payload: dict[str, str],
    fake_api_key: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regresión: dos tools en paralelo compartían la sesión de BD y PostgreSQL fallaba."""
    created = client.post("/tickets", json=ticket_payload).json()

    active = 0
    max_active = 0
    lock = threading.Lock()

    def track(original):  # envuelve una función del service para medir solapamientos
        def wrapper(*args, **kwargs):
            nonlocal active, max_active
            with lock:
                active += 1
                max_active = max(max_active, active)
            time.sleep(0.05)  # da tiempo a que otra tool se solape si fuera posible
            try:
                return original(*args, **kwargs)
            finally:
                with lock:
                    active -= 1

        return wrapper

    monkeypatch.setattr(ticket_service, "list_tickets", track(ticket_service.list_tickets))
    monkeypatch.setattr(ticket_service, "search_tickets", track(ticket_service.search_tickets))

    def both_tools_at_once(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if len(messages) == 1:
            # Como hizo Gemini de verdad: pide las dos tools en la MISMA respuesta
            return ModelResponse(
                parts=[
                    ToolCallPart("get_customer_history", {}),
                    ToolCallPart("search_similar_tickets", {"keywords": "sesión"}),
                ]
            )
        return ModelResponse(
            parts=[
                ToolCallPart(
                    "final_result",
                    {"priority": "low", "category": "other", "summary": "s", "suggested_reply": "r"},
                )
            ]
        )

    with triage_agent.override(model=FunctionModel(both_tools_at_once)):
        response = client.post(f"/tickets/{created['id']}/triage")

    assert response.status_code == 200
    assert max_active == 1


def test_triage_with_test_model_calls_all_tools(
    client: TestClient, ticket_payload: dict[str, str], fake_api_key: None
) -> None:
    created = client.post("/tickets", json=ticket_payload).json()

    with triage_agent.override(model=TestModel()):
        response = client.post(f"/tickets/{created['id']}/triage")

    assert response.status_code == 200
    data = response.json()
    assert data["priority"] is not None
    assert data["category"] is not None


def test_triage_model_error_returns_503(
    client: TestClient, ticket_payload: dict[str, str], fake_api_key: None
) -> None:
    created = client.post("/tickets", json=ticket_payload).json()

    def broken_model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        raise UnexpectedModelBehavior("el modelo devolvió basura")

    with triage_agent.override(model=FunctionModel(broken_model)):
        response = client.post(f"/tickets/{created['id']}/triage")

    assert response.status_code == 503
    # El ticket no se modificó
    assert client.get(f"/tickets/{created['id']}").json()["priority"] is None


def test_triage_without_api_key_returns_503(
    client: TestClient, ticket_payload: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "ai_model", "google:gemini-3.8-flash")
    monkeypatch.setattr(settings, "google_api_key", None)
    created = client.post("/tickets", json=ticket_payload).json()

    response = client.post(f"/tickets/{created['id']}/triage")

    assert response.status_code == 503
    assert "GOOGLE_API_KEY" in response.json()["detail"]


def test_triage_ticket_not_found(client: TestClient) -> None:
    assert client.post("/tickets/999/triage").status_code == 404


def test_search_tickets(session: Session) -> None:
    login = ticket_service.create_ticket(
        session,
        TicketCreate(subject="No puedo iniciar sesión", body="Error 500", customer_email="a@x.com"),
    )
    ticket_service.create_ticket(
        session,
        TicketCreate(subject="Factura", body="Cobro doble", customer_email="b@x.com"),
    )

    # Ojo: SQLite solo ignora mayúsculas en letras ASCII ("Ó" ≠ "ó"); PostgreSQL sí las iguala
    found = ticket_service.search_tickets(session, "INICIAR sesión")

    assert [t.id for t in found] == [login.id]
    assert ticket_service.search_tickets(session, "iniciar", exclude_id=login.id) == []


def test_list_tickets_filter_by_customer(
    client: TestClient, ticket_payload: dict[str, str]
) -> None:
    client.post("/tickets", json=ticket_payload)
    client.post("/tickets", json={**ticket_payload, "customer_email": "otro@example.com"})

    response = client.get("/tickets", params={"customer_email": "otro@example.com"})

    assert [t["customer_email"] for t in response.json()] == ["otro@example.com"]
