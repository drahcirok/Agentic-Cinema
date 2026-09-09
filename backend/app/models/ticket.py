from datetime import datetime
from enum import StrEnum
from urllib.parse import urlparse
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator


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
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    READY_FOR_QC = "ready_for_qc"
    COMPLETED = "completed"
    # Kept only to render tickets created before Workflow v1. New approvals
    # transition to ASSIGNED.
    APPROVED = "approved"
    REJECTED = "rejected"


class ReviewDecision(StrEnum):
    APPROVE = "approve"
    EDIT = "edit"
    REJECT = "reject"


class ArtistWorkStatus(StrEnum):
    IN_PROGRESS = "in_progress"
    READY_FOR_QC = "ready_for_qc"


class QualityDecision(StrEnum):
    APPROVE = "approve"
    RETURN_FOR_REWORK = "return_for_rework"


class TicketCreate(BaseModel):
    shot_id: str = Field(min_length=1, max_length=64, examples=["SC03-SH014"])
    director_note: str = Field(min_length=1, examples=["Remove the microphone from the frame."])
    department: Department
    priority: Priority = Priority.MEDIUM
    ai_rationale: str | None = None


class TicketReview(BaseModel):
    decision: ReviewDecision
    department: Department | None = None
    priority: Priority | None = None
    supervisor_note: str | None = Field(default=None, max_length=1000)
    assigned_to_uid: str | None = Field(default=None, min_length=1, max_length=128)
    assigned_to_name: str | None = Field(default=None, max_length=120)


class TicketWorkUpdate(BaseModel):
    status: ArtistWorkStatus
    artist_note: str | None = Field(default=None, max_length=1000)
    delivery_link: str | None = Field(default=None, max_length=2048)

    @field_validator("delivery_link")
    @classmethod
    def validate_delivery_link(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("The delivery link must use http:// or https://.")
        return value


class TicketQualityReview(BaseModel):
    decision: QualityDecision
    supervisor_feedback: str | None = Field(default=None, max_length=1000)


class Ticket(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    shot_id: str
    director_note: str
    department: Department
    priority: Priority
    status: TicketStatus = TicketStatus.PENDING_REVIEW
    ai_rationale: str | None = None
    supervisor_note: str | None = None
    artist_note: str | None = None
    delivery_link: str | None = None
    evidence_gcs_uri: str | None = None
    evidence_name: str | None = None
    evidence_content_type: str | None = None
    supervisor_feedback: str | None = None
    # The production becomes the collaboration/security boundary. ``None`` is
    # retained only to render historical tickets created before team support.
    production_id: UUID | None = None
    assigned_to_uid: str | None = None
    assigned_to_name: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
