from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import DateTime
from sqlmodel import Field, SQLModel


class TicketStatus(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"


class TicketPriority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class TicketCategory(StrEnum):
    BILLING = "billing"
    TECHNICAL = "technical"
    ACCOUNT = "account"
    OTHER = "other"


def utc_now() -> datetime:
    return datetime.now(UTC)


class Ticket(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)

    subject: str = Field(max_length=200)
    body: str
    customer_email: str = Field(max_length=320)
    # Lowercased, accent-free subject + body so search matches "sesion" and "Sesión" alike.
    search_text: str = ""

    status: TicketStatus = Field(default=TicketStatus.OPEN, index=True)

    # Filled in by the triage agent.
    priority: TicketPriority | None = Field(default=None, index=True)
    category: TicketCategory | None = Field(default=None, index=True)
    summary: str | None = None
    suggested_reply: str | None = None

    created_at: datetime = Field(default_factory=utc_now, sa_type=DateTime(timezone=True))
    updated_at: datetime = Field(default_factory=utc_now, sa_type=DateTime(timezone=True))
