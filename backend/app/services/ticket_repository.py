"""SQLAlchemy-backed repository for post-production tickets.

Replaces the in-memory TicketStore.  All public methods mirror the
TicketStore interface so callers require only minimal changes.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.ticket import ReviewDecision, Ticket, TicketCreate, TicketReview, TicketStatus
from app.models.ticket_record import TicketRecord


class TicketNotFoundError(Exception):
    """The requested ticket does not exist in the database."""


def _record_to_ticket(record: TicketRecord) -> Ticket:
    """Convert an ORM row to the Pydantic API model."""
    return Ticket(
        id=UUID(record.id),
        shot_id=record.shot_id,
        director_note=record.director_note,
        department=record.department,
        priority=record.priority,
        status=record.status,
        ai_rationale=record.ai_rationale,
        supervisor_note=record.supervisor_note,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


class TicketRepository:
    """Persists tickets to SQLite via a SQLAlchemy session."""

    def __init__(self, db: Session) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def create(self, payload: TicketCreate) -> Ticket:
        """Insert a new ticket and return the Pydantic representation."""
        from uuid import uuid4

        now = datetime.now(timezone.utc)
        record = TicketRecord(
            id=str(uuid4()),
            shot_id=payload.shot_id,
            director_note=payload.director_note,
            department=str(payload.department),
            priority=str(payload.priority),
            status=str(TicketStatus.PENDING_REVIEW),
            ai_rationale=payload.ai_rationale,
            supervisor_note=None,
            created_at=now,
            updated_at=now,
        )
        self._db.add(record)
        self._db.commit()
        self._db.refresh(record)
        return _record_to_ticket(record)

    def review(self, ticket_id: UUID, review: TicketReview) -> Ticket:
        """Apply a supervisor review decision and return the updated ticket."""
        record: TicketRecord | None = self._db.get(TicketRecord, str(ticket_id))
        if record is None:
            raise TicketNotFoundError(f"Ticket {ticket_id} not found")

        if review.department is not None:
            record.department = str(review.department)
        if review.priority is not None:
            record.priority = str(review.priority)
        if review.supervisor_note is not None:
            record.supervisor_note = review.supervisor_note

        if review.decision is ReviewDecision.APPROVE:
            record.status = str(TicketStatus.APPROVED)
        elif review.decision is ReviewDecision.REJECT:
            record.status = str(TicketStatus.REJECTED)
        else:
            record.status = str(TicketStatus.PENDING_REVIEW)

        record.updated_at = datetime.now(timezone.utc)
        self._db.commit()
        self._db.refresh(record)
        return _record_to_ticket(record)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def list(self) -> list[Ticket]:
        """Return all tickets ordered by creation date descending."""
        records = (
            self._db.query(TicketRecord)
            .order_by(TicketRecord.created_at.desc())
            .all()
        )
        return [_record_to_ticket(r) for r in records]
