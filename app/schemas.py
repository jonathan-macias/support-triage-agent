"""Schemas de la API (lo que entra y sale por HTTP).

Son modelos de Pydantic: FastAPI los usa para
  1. validar el JSON que llega (si falta un campo o el email es inválido,
     responde 422 automáticamente, sin que escribamos ese código),
  2. filtrar/convertir lo que devolvemos,
  3. generar la documentación en /docs.

Separarlos de `models.py` permite que la tabla tenga campos internos que el
cliente no puede enviar (id, fechas, status inicial...).
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models import TicketCategory, TicketPriority, TicketStatus


class TicketCreate(BaseModel):
    """Lo que el cliente envía para abrir un ticket."""

    subject: str = Field(min_length=1, max_length=200, examples=["No puedo iniciar sesión"])
    body: str = Field(
        min_length=1,
        examples=["Desde ayer me sale 'contraseña incorrecta' aunque la acabo de cambiar."],
    )
    customer_email: EmailStr = Field(examples=["cliente@example.com"])


class TicketUpdate(BaseModel):
    """Actualización parcial (PATCH): todos los campos son opcionales.

    Solo se modifican los campos que vengan en el JSON.
    """

    status: TicketStatus | None = None
    priority: TicketPriority | None = None
    category: TicketCategory | None = None
    summary: str | None = None
    suggested_reply: str | None = None

    # Un validador personalizado: `priority: null` es válido (borra la prioridad),
    # pero un ticket siempre debe tener status, así que `status: null` → 422.
    @field_validator("status")
    @classmethod
    def status_not_null(cls, value: TicketStatus | None) -> TicketStatus:
        if value is None:
            raise ValueError("status no puede ser null")
        return value


class TicketRead(BaseModel):
    """Lo que la API devuelve."""

    # Permite construir este schema a partir de un objeto `Ticket` de la BD
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
