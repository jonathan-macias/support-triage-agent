"""MCP server tests through a real MCP client connected in-process."""

from collections.abc import AsyncIterator

import pytest
from mcp.client import Client
from pydantic_ai.models.test import TestModel
from sqlalchemy import Engine
from sqlmodel import Session

from app import database
from app.agent.triage import triage_agent
from app.config import settings
from app.mcp_server import mcp
from app.models import TicketCategory, TicketPriority, TicketStatus
from app.schemas import TicketCreate
from app.services import tickets as ticket_service

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def client(engine: Engine, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Client]:
    monkeypatch.setattr(database, "engine", engine)
    async with Client(mcp) as client:
        yield client


def _create(session: Session, subject: str, email: str = "ana@example.com") -> int:
    ticket = ticket_service.create_ticket(
        session, TicketCreate(subject=subject, body=f"Body of {subject}", customer_email=email)
    )
    assert ticket.id is not None
    return ticket.id


async def test_lists_all_tools_with_annotations(client: Client) -> None:
    tools = {tool.name: tool for tool in (await client.list_tools()).tools}

    assert set(tools) == {
        "list_tickets",
        "get_ticket",
        "search_tickets",
        "get_customer_history",
        "triage_ticket",
        "update_ticket_status",
    }
    assert tools["list_tickets"].annotations.read_only_hint is True
    assert tools["update_ticket_status"].annotations.read_only_hint is False
    assert tools["update_ticket_status"].annotations.destructive_hint is False


async def test_enum_values_are_spelled_out_in_descriptions(client: Client) -> None:
    """Some hosts drop `$ref`/`anyOf`, so descriptions must list the allowed values."""
    tools = {tool.name: tool for tool in (await client.list_tools()).tools}
    expected = {
        ("list_tickets", "status"): TicketStatus,
        ("list_tickets", "priority"): TicketPriority,
        ("list_tickets", "category"): TicketCategory,
        ("update_ticket_status", "status"): TicketStatus,
    }

    for (tool_name, param), enum in expected.items():
        description = tools[tool_name].input_schema["properties"][param]["description"]
        assert all(value in description for value in enum), (tool_name, param)


async def test_list_and_get_ticket(client: Client, session: Session) -> None:
    ticket_id = _create(session, "Cannot log in")

    listed = await client.call_tool("list_tickets", {})
    fetched = await client.call_tool("get_ticket", {"ticket_id": ticket_id})

    assert [t["id"] for t in listed.structured_content["result"]] == [ticket_id]
    assert fetched.structured_content["subject"] == "Cannot log in"


async def test_get_missing_ticket_is_tool_error(client: Client) -> None:
    result = await client.call_tool("get_ticket", {"ticket_id": 999})

    assert result.is_error
    assert "Ticket 999 not found" in result.content[0].text


async def test_search_and_customer_history(client: Client, session: Session) -> None:
    login_id = _create(session, "Cannot log in", email="ana@example.com")
    _create(session, "Invoice error", email="ana@example.com")
    _create(session, "Dark mode please", email="bob@example.com")

    found = await client.call_tool("search_tickets", {"keywords": "LOG IN"})
    history = await client.call_tool("get_customer_history", {"customer_email": "ana@example.com"})

    assert [t["id"] for t in found.structured_content["result"]] == [login_id]
    assert len(history.structured_content["result"]) == 2


async def test_update_ticket_status(client: Client, session: Session) -> None:
    ticket_id = _create(session, "Cannot log in")

    result = await client.call_tool(
        "update_ticket_status", {"ticket_id": ticket_id, "status": "resolved"}
    )

    assert result.structured_content["status"] == "resolved"


async def test_invalid_status_is_rejected(client: Client, session: Session) -> None:
    ticket_id = _create(session, "Cannot log in")

    result = await client.call_tool(
        "update_ticket_status", {"ticket_id": ticket_id, "status": "deleted"}
    )

    assert result.is_error


async def test_triage_ticket_runs_agent(
    client: Client, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "google_api_key", "test-key")
    ticket_id = _create(session, "Cannot log in")

    with triage_agent.override(model=TestModel()):
        result = await client.call_tool("triage_ticket", {"ticket_id": ticket_id})

    assert not result.is_error
    assert result.structured_content["priority"] is not None


async def test_triage_without_api_key_is_tool_error(
    client: Client, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "ai_model", "google:gemini-3.5-flash-lite")
    monkeypatch.setattr(settings, "google_api_key", None)
    ticket_id = _create(session, "Cannot log in")

    result = await client.call_tool("triage_ticket", {"ticket_id": ticket_id})

    assert result.is_error
    assert "GOOGLE_API_KEY" in result.content[0].text
