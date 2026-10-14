"""Endpoints HTTP de /tickets.

Un router agrupa rutas relacionadas. Cada función decorada con
`@router.get/post/...` es un endpoint. Los endpoints son "finos": traducen
HTTP ↔ Python y delegan el trabajo real en `app.services.tickets`.
"""

from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app.database import SessionDep
from app.models import Ticket, TicketCategory, TicketPriority, TicketStatus
from app.schemas import TicketCreate, TicketRead, TicketUpdate
from app.services import tickets as service

router = APIRouter(prefix="/tickets", tags=["tickets"])


def get_ticket_or_404(ticket_id: int, session: SessionDep) -> Ticket:
    """Dependencia: busca el ticket de la URL o corta la petición con 404.

    Como `ticket_id` coincide con `{ticket_id}` en la ruta, FastAPI lo toma de
    la URL y lo convierte a int (si no es un número → 422).
    """
    ticket = service.get_ticket(session, ticket_id)
    if ticket is None:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Ticket no encontrado")
    return ticket


TicketDep = Annotated[Ticket, Depends(get_ticket_or_404)]


@router.post("", response_model=TicketRead, status_code=HTTPStatus.CREATED)
def create_ticket(data: TicketCreate, session: SessionDep) -> Ticket:
    # `data: TicketCreate` → FastAPI lee el JSON del body y lo valida con Pydantic
    return service.create_ticket(session, data)


@router.get("", response_model=list[TicketRead])
def list_tickets(
    session: SessionDep,
    # Parámetros de query: /tickets?status=open&limit=10
    status: TicketStatus | None = None,
    priority: TicketPriority | None = None,
    category: TicketCategory | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[Ticket]:
    return service.list_tickets(
        session, status=status, priority=priority, category=category, limit=limit, offset=offset
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
