"""SQLAlchemy ORM model for post-production tickets.

This module is intentionally separate from app/models/ticket.py, which owns
the Pydantic API contracts.  Mixing the two would couple persistence details
to the public schema.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _utcnow() -> datetime:
    """Return the current time as a timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# ORM model
# ---------------------------------------------------------------------------


class TicketRecord(Base):
    """Persisted representation of a post-production ticket.

    Field values for ``department``, ``priority``, and ``status`` must match
    the string values of the corresponding Pydantic enums in ticket.py
    (e.g. ``"vfx"``, ``"medium"``, ``"pending_review"``).
    """

    __tablename__ = "postproduction_tickets"

    # Primary key stored as a plain UUID string for SQLite compatibility.
    id: Mapped[str] = mapped_column(String(36), primary_key=True)

    # Firebase UID del supervisor propietario. Se deja nullable para que la
    # migración local no destruya tickets antiguos; esos tickets no se muestran
    # cuando la autenticación está activa.
    owner_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    production_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    assigned_to_uid: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    assigned_to_name: Mapped[str | None] = mapped_column(String(120), nullable=True)

    shot_id: Mapped[str] = mapped_column(String(64), nullable=False)
    director_note: Mapped[str] = mapped_column(Text, nullable=False)

    # Enum values stored as strings; must match Pydantic StrEnum values.
    department: Mapped[str] = mapped_column(String(32), nullable=False)
    priority: Mapped[str] = mapped_column(String(16), nullable=False, default="medium")
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending_review"
    )

    ai_rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    supervisor_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    artist_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    delivery_link: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_gcs_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    evidence_content_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    supervisor_feedback: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        onupdate=_utcnow,
    )

    # ---------------------------------------------------------------------------
    # Indexes
    # ---------------------------------------------------------------------------

    __table_args__ = (
        Index("ix_postproduction_tickets_status", "status"),
        Index("ix_postproduction_tickets_created_at", "created_at"),
    )
