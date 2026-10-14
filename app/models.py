"""Modelos de base de datos (tablas).

Una clase con `table=True` es una tabla de PostgreSQL. Cada atributo con su
type hint es una columna. Estos modelos describen CÓMO SE GUARDAN los datos;
lo que la API recibe y devuelve está en `schemas.py`.
"""

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
    # `int | None` porque antes de guardarlo aún no tiene id; PostgreSQL lo asigna.
    id: int | None = Field(default=None, primary_key=True)

    # Datos que envía el cliente
    subject: str = Field(max_length=200)
    body: str
    customer_email: str = Field(max_length=320)

    # Estado del flujo de soporte. `index=True` acelera los filtros por esta columna.
    status: TicketStatus = Field(default=TicketStatus.OPEN, index=True)

    # Campos que rellenará el agente de IA en la fase 2 (por eso pueden ser None)
    priority: TicketPriority | None = Field(default=None, index=True)
    category: TicketCategory | None = Field(default=None, index=True)
    summary: str | None = None
    suggested_reply: str | None = None

    # `default_factory` llama a la función cada vez que se crea un ticket
    created_at: datetime = Field(default_factory=utc_now, sa_type=DateTime(timezone=True))
    updated_at: datetime = Field(default_factory=utc_now, sa_type=DateTime(timezone=True))
