"""Public contracts for a ticket's immutable workflow timeline."""

from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class TicketActivity(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    ticket_id: UUID
    production_id: UUID | None = None
    actor_uid: str
    actor_name: str | None = None
    action: str
    detail: str | None = None
    created_at: datetime
