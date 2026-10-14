"""Triage agent tests: `triage_agent.override(model=...)` swaps in a fake model,
so no real LLM is ever called."""

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
    # build_model() requires a key; the overridden model means it is never used.
    monkeypatch.setattr(settings, "google_api_key", "test-key")
    yield


def scripted_model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    """Fake model: first asks for the customer history, then returns the result."""
    tool_returns = [
        part for message in messages for part in message.parts if isinstance(part, ToolReturnPart)
    ]
    if not tool_returns:
        return ModelResponse(parts=[ToolCallPart("get_customer_history", {})])

    # Structured output is returned through the "final_result" output tool.
    history = tool_returns[0].content
    priority = "high" if history else "medium"
    return ModelResponse(
        parts=[
            ToolCallPart(
                "final_result",
                {
                    "priority": priority,
                    "category": "billing",
                    "summary": "Customer is chasing an invoice error again.",
                    "suggested_reply": "Hi, sorry for the trouble. We are looking into it.",
                },
            )
        ]
    )


def test_triage_saves_agent_result(
    client: TestClient, session: Session, fake_api_key: None
) -> None:
    email = "marta@example.com"
    ticket_service.create_ticket(
        session, TicketCreate(subject="Wrong invoice", body="Incorrect amount", customer_email=email)
    )
    current = ticket_service.create_ticket(
        session, TicketCreate(subject="Still waiting", body="Nobody answered", customer_email=email)
    )

    with triage_agent.override(model=FunctionModel(scripted_model)):
        response = client.post(f"/tickets/{current.id}/triage")

    assert response.status_code == 200
    data = response.json()
    # "high" because the tool found a previous ticket from the same customer
    assert data["priority"] == "high"
    assert data["category"] == "billing"
    assert data["summary"].startswith("Customer is chasing")
    assert data["suggested_reply"]
    # ...and it was persisted
    assert client.get(f"/tickets/{current.id}").json()["priority"] == "high"


def test_tools_never_run_concurrently(
    client: TestClient,
    ticket_payload: dict[str, str],
    fake_api_key: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: parallel tools shared one DB session and broke the PostgreSQL transaction."""
    created = client.post("/tickets", json=ticket_payload).json()

    active = 0
    max_active = 0
    lock = threading.Lock()

    def track(original):  # wraps a service function to measure overlapping calls
        def wrapper(*args, **kwargs):
            nonlocal active, max_active
            with lock:
                active += 1
                max_active = max(max_active, active)
            time.sleep(0.05)  # gives another tool time to overlap, if it could
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
            # As Gemini did in production: both tools in the SAME response
            return ModelResponse(
                parts=[
                    ToolCallPart("get_customer_history", {}),
                    ToolCallPart("search_similar_tickets", {"keywords": "log in"}),
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
        raise UnexpectedModelBehavior("garbage output")

    with triage_agent.override(model=FunctionModel(broken_model)):
        response = client.post(f"/tickets/{created['id']}/triage")

    assert response.status_code == 503
    # The ticket was left untouched
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
        TicketCreate(subject="Cannot log in", body="Error 500", customer_email="a@x.com"),
    )
    ticket_service.create_ticket(
        session,
        TicketCreate(subject="Invoice", body="Charged twice", customer_email="b@x.com"),
    )

    found = ticket_service.search_tickets(session, "LOG IN")

    assert [t.id for t in found] == [login.id]
    assert ticket_service.search_tickets(session, "log", exclude_id=login.id) == []


def test_list_tickets_filter_by_customer(
    client: TestClient, ticket_payload: dict[str, str]
) -> None:
    client.post("/tickets", json=ticket_payload)
    client.post("/tickets", json={**ticket_payload, "customer_email": "other@example.com"})

    response = client.get("/tickets", params={"customer_email": "other@example.com"})

    assert [t["customer_email"] for t in response.json()] == ["other@example.com"]
