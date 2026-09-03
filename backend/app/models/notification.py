"""Public notification contracts for FrameFlow."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class NotificationType(StrEnum):
    INVITATION = "invitation"
    TASK_ASSIGNED = "task_assigned"
    QC_READY = "qc_ready"
    QC_RETURNED = "qc_returned"
    QC_COMPLETED = "qc_completed"


class Notification(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    recipient_uid: str
    type: NotificationType
    title: str
    message: str
    production_id: UUID | None = None
    ticket_id: UUID | None = None
    created_at: datetime
    read_at: datetime | None = None
