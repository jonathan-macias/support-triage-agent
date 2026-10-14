from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic_ai.exceptions import AgentRunError

from app.agent.triage import MissingApiKeyError
from app.database import SessionDep
from app.models import Ticket, TicketCategory, TicketPriority, TicketStatus
from app.schemas import TicketCreate, TicketRead, TicketUpdate
from app.services import tickets as service
from app.services.triage import triage_ticket

router = APIRouter(prefix="/tickets", tags=["tickets"])


def get_ticket_or_404(ticket_id: int, session: SessionDep) -> Ticket:
    ticket = service.get_ticket(session, ticket_id)
    if ticket is None:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Ticket not found")
    return ticket


TicketDep = Annotated[Ticket, Depends(get_ticket_or_404)]


@router.post("", response_model=TicketRead, status_code=HTTPStatus.CREATED)
def create_ticket(data: TicketCreate, session: SessionDep) -> Ticket:
    return service.create_ticket(session, data)


@router.get("", response_model=list[TicketRead])
def list_tickets(
    session: SessionDep,
    status: TicketStatus | None = None,
    priority: TicketPriority | None = None,
    category: TicketCategory | None = None,
    customer_email: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[Ticket]:
    return service.list_tickets(
        session,
        status=status,
        priority=priority,
        category=category,
        customer_email=customer_email,
        limit=limit,
        offset=offset,
    )


@router.get("/{ticket_id}", response_model=TicketRead)
def read_ticket(ticket: TicketDep) -> Ticket:
    return ticket


@router.patch("/{ticket_id}", response_model=TicketRead)
def update_ticket(ticket: TicketDep, changes: TicketUpdate, session: SessionDep) -> Ticket:
    return service.update_ticket(session, ticket, changes)


@router.delete("/{ticket_id}", status_code=HTTPStatus.NO_CONTENT)
def delete_ticket(ticket: TicketDep, session: SessionDep) -> None:
    service.delete_ticket(session, ticket)


@router.post("/{ticket_id}/triage", response_model=TicketRead)
async def triage(ticket: TicketDep, session: SessionDep) -> Ticket:
    """Classify the ticket with the AI agent and store the result."""
    try:
        return await triage_ticket(session, ticket)
    except MissingApiKeyError as exc:
        raise HTTPException(status_code=HTTPStatus.SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except AgentRunError as exc:
        # Provider outage, rate limit, invalid model output or usage limit exceeded.
        raise HTTPException(
            status_code=HTTPStatus.SERVICE_UNAVAILABLE,
            detail=f"The AI agent could not complete the triage: {exc}",
        ) from exc
