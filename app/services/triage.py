"""Caso de uso "hacer triage de un ticket": ejecuta el agente y guarda el resultado."""

from sqlmodel import Session

from app.agent.triage import run_triage
from app.models import Ticket
from app.schemas import TicketUpdate
from app.services.tickets import update_ticket


async def triage_ticket(session: Session, ticket: Ticket) -> Ticket:
    result = await run_triage(session, ticket)
    # Reutilizamos update_ticket: el resultado del agente es solo otra actualización
    changes = TicketUpdate(**result.model_dump())
    return update_ticket(session, ticket, changes)
