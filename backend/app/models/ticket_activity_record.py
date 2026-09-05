"""SQLite persistence model for the audit trail of each ticket."""

from datetime import datetime, timezone

from sqlalchemy import DateTime, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TicketActivityRecord(Base):
    __tablename__ = "ticket_activity"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    ticket_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    production_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    actor_uid: Mapped[str] = mapped_column(String(128), nullable=False)
    actor_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    action: Mapped[str] = mapped_column(String(160), nullable=False)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)

    __table_args__ = (Index("ix_ticket_activity_ticket_created", "ticket_id", "created_at"),)
