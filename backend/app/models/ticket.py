from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class Department(StrEnum):
    VFX = "vfx"
    COLOR = "color"
    SOUND = "sound"
    EDITORIAL = "editorial"


class Priority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TicketStatus(StrEnum):
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"


class ReviewDecision(StrEnum):
    APPROVE = "approve"
    EDIT = "edit"
    REJECT = "reject"


class TicketCreate(BaseModel):
    shot_id: str = Field(min_length=1, max_length=64, examples=["SC03-SH014"])
    director_note: str = Field(min_length=1, examples=["Eliminar el micrófono del encuadre."])
    department: Department
    priority: Priority = Priority.MEDIUM
    ai_rationale: str | None = None


class TicketReview(BaseModel):
    decision: ReviewDecision
    department: Department | None = None
    priority: Priority | None = None
    supervisor_note: str | None = Field(default=None, max_length=1000)


class Ticket(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    shot_id: str
    director_note: str
    department: Department
    priority: Priority
    status: TicketStatus = TicketStatus.PENDING_REVIEW
    ai_rationale: str | None = None
    supervisor_note: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
