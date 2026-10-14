"""Lógica de negocio de los tickets.

Aquí NO hay nada de HTTP (ni códigos 404, ni requests). Son funciones normales
de Python que reciben una sesión de BD y datos. Esto es importante para las
siguientes fases: las *tools* del agente de IA y el servidor MCP llamarán a
estas mismas funciones, sin pasar por la API web.
"""

from sqlmodel import Session, or_, select

from app.models import Ticket, TicketCategory, TicketPriority, TicketStatus, utc_now
from app.schemas import TicketCreate, TicketUpdate


def create_ticket(session: Session, data: TicketCreate) -> Ticket:
    ticket = Ticket(**data.model_dump())
    session.add(ticket)
    session.commit()  # guarda en la BD
    session.refresh(ticket)  # recarga el objeto para obtener el id generado
    return ticket


def get_ticket(session: Session, ticket_id: int) -> Ticket | None:
    return session.get(Ticket, ticket_id)


def list_tickets(
    session: Session,
    *,  # todo lo que va después del * debe pasarse por nombre: list_tickets(s, status=...)
    status: TicketStatus | None = None,
    priority: TicketPriority | None = None,
    category: TicketCategory | None = None,
    customer_email: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Ticket]:
    # `select(Ticket)` construye la consulta SQL "SELECT ... FROM ticket"
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
    """Busca tickets cuyo asunto o cuerpo contengan `text` (sin distinguir mayúsculas)."""
    pattern = f"%{text}%"  # en SQL, % significa "cualquier cosa"
    query = select(Ticket).where(
        or_(Ticket.subject.ilike(pattern), Ticket.body.ilike(pattern))
    )
    if exclude_id is not None:
        query = query.where(Ticket.id != exclude_id)

    query = query.order_by(Ticket.id.desc()).limit(limit)
    return list(session.exec(query).all())


def update_ticket(session: Session, ticket: Ticket, changes: TicketUpdate) -> Ticket:
    # exclude_unset=True → solo los campos que el cliente envió de verdad
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
