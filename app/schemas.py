"""Request and response schemas, kept separate from the table model so clients
can't set server-managed fields (id, timestamps, initial status)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models import TicketCategory, TicketPriority, TicketStatus


class TicketCreate(BaseModel):
    subject: str = Field(min_length=1, max_length=200, examples=["I can't log in"])
    body: str = Field(
        min_length=1,
        examples=["Since yesterday I get 'wrong password' even though I just reset it."],
    )
    customer_email: EmailStr = Field(examples=["customer@example.com"])


class TicketUpdate(BaseModel):
    """Partial update: only the fields present in the request are changed."""

    status: TicketStatus | None = None
    priority: TicketPriority | None = None
    category: TicketCategory | None = None
    summary: str | None = None
    suggested_reply: str | None = None

    # `priority: null` clears the priority, but a ticket must always have a status.
    @field_validator("status")
    @classmethod
    def status_not_null(cls, value: TicketStatus | None) -> TicketStatus:
        if value is None:
            raise ValueError("status cannot be null")
        return value


class TicketRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    subject: str
    body: str
    customer_email: str
    status: TicketStatus
    priority: TicketPriority | None
    category: TicketCategory | None
    summary: str | None
    suggested_reply: str | None
    created_at: datetime
    updated_at: datetime
