from sqlmodel import Session

from app.agent.triage import run_triage
from app.models import Ticket
from app.schemas import TicketUpdate
from app.services.tickets import update_ticket


async def triage_ticket(session: Session, ticket: Ticket) -> Ticket:
    """Run the triage agent on a ticket and persist its result."""
    result = await run_triage(session, ticket)
    return update_ticket(session, ticket, TicketUpdate(**result.model_dump()))
