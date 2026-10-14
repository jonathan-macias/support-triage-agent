"""Ticket business logic, free of HTTP concerns so the API, the agent tools and
the MCP server can all share it."""

import unicodedata

from sqlmodel import Session, select

from app.models import Ticket, TicketCategory, TicketPriority, TicketStatus, utc_now
from app.schemas import TicketCreate, TicketUpdate


def normalize_text(text: str) -> str:
    """Casefold and strip accents: "Iniciar Sesión" -> "iniciar sesion"."""
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def create_ticket(session: Session, data: TicketCreate) -> Ticket:
    ticket = Ticket(**data.model_dump(), search_text=normalize_text(f"{data.subject} {data.body}"))
    session.add(ticket)
    session.commit()
    session.refresh(ticket)
    return ticket


def get_ticket(session: Session, ticket_id: int) -> Ticket | None:
    return session.get(Ticket, ticket_id)


def list_tickets(
    session: Session,
    *,
    status: TicketStatus | None = None,
    priority: TicketPriority | None = None,
    category: TicketCategory | None = None,
    customer_email: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Ticket]:
    query = select(Ticket)
    if status is not None:
        query = query.where(Ticket.status == status)
    if priority is not None:
        query = query.where(Ticket.priority == priority)
    if category is not None:
        query = query.where(Ticket.category == category)
    if customer_email is not None:
        query = query.where(Ticket.customer_email == customer_email)

    query = query.order_by(Ticket.id.desc()).offset(offset).limit(limit)
    return list(session.exec(query).all())


def search_tickets(
    session: Session, text: str, *, exclude_id: int | None = None, limit: int = 5
) -> list[Ticket]:
    """Case- and accent-insensitive substring search over subject and body."""
    # autoescape: a "%" or "_" typed by the caller is matched literally, not as a wildcard.
    query = select(Ticket).where(Ticket.search_text.contains(normalize_text(text), autoescape=True))
    if exclude_id is not None:
        query = query.where(Ticket.id != exclude_id)

    query = query.order_by(Ticket.id.desc()).limit(limit)
    return list(session.exec(query).all())


def update_ticket(session: Session, ticket: Ticket, changes: TicketUpdate) -> Ticket:
    for field, value in changes.model_dump(exclude_unset=True).items():
        setattr(ticket, field, value)
    ticket.updated_at = utc_now()

    session.add(ticket)
    session.commit()
    session.refresh(ticket)
    return ticket


def delete_ticket(session: Session, ticket: Ticket) -> None:
    session.delete(ticket)
    session.commit()
