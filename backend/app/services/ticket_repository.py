"""Persistence repositories for post-production tickets.

SQLite is used in local development and Firestore in Cloud Run. Both expose
the same small contract so the API layer stays storage-agnostic.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.ticket import ReviewDecision, Ticket, TicketCreate, TicketReview, TicketStatus
from app.models.ticket_record import TicketRecord


class TicketNotFoundError(Exception):
    """The requested ticket does not exist in the database."""


class TicketDataRepository(Protocol):
    """Common persistence operations exposed to FastAPI endpoints."""

    def create(self, payload: TicketCreate) -> Ticket: ...

    def review(self, ticket_id: UUID, review: TicketReview) -> Ticket: ...

    def list(self) -> list[Ticket]: ...


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


class FirestoreTicketRepository:
    """Firestore-backed ticket repository authenticated through ADC."""

    def __init__(self, client: object | None = None, collection_name: str | None = None) -> None:
        settings.validate_ticket_storage()
        self._client = client
        self._collection_name = collection_name or settings.firestore_collection

    def _get_client(self) -> object:
        if self._client is None:
            from google.cloud import firestore

            self._client = firestore.Client(project=settings.google_cloud_project)
        return self._client

    def _get_collection(self) -> object:
        return self._get_client().collection(self._collection_name)  # type: ignore[union-attr,no-any-return]

    @staticmethod
    def _document_to_ticket(document_id: str, data: dict[str, object]) -> Ticket:
        return Ticket(
            id=UUID(document_id),
            shot_id=str(data["shot_id"]),
            director_note=str(data["director_note"]),
            department=str(data["department"]),
            priority=str(data["priority"]),
            status=str(data["status"]),
            ai_rationale=data.get("ai_rationale"),  # type: ignore[arg-type]
            supervisor_note=data.get("supervisor_note"),  # type: ignore[arg-type]
            created_at=data["created_at"],  # type: ignore[arg-type]
            updated_at=data["updated_at"],  # type: ignore[arg-type]
        )

    def create(self, payload: TicketCreate) -> Ticket:
        from uuid import uuid4

        ticket_id = uuid4()
        now = datetime.now(timezone.utc)
        data: dict[str, object] = {
            "shot_id": payload.shot_id,
            "director_note": payload.director_note,
            "department": str(payload.department),
            "priority": str(payload.priority),
            "status": str(TicketStatus.PENDING_REVIEW),
            "ai_rationale": payload.ai_rationale,
            "supervisor_note": None,
            "created_at": now,
            "updated_at": now,
        }
        self._get_collection().document(str(ticket_id)).set(data)  # type: ignore[union-attr]
        return self._document_to_ticket(str(ticket_id), data)

    def review(self, ticket_id: UUID, review: TicketReview) -> Ticket:
        reference = self._get_collection().document(str(ticket_id))  # type: ignore[union-attr]
        snapshot = reference.get()
        if not snapshot.exists:
            raise TicketNotFoundError(f"Ticket {ticket_id} not found")

        changes: dict[str, object] = {"updated_at": datetime.now(timezone.utc)}
        if review.department is not None:
            changes["department"] = str(review.department)
        if review.priority is not None:
            changes["priority"] = str(review.priority)
        if review.supervisor_note is not None:
            changes["supervisor_note"] = review.supervisor_note

        if review.decision is ReviewDecision.APPROVE:
            changes["status"] = str(TicketStatus.APPROVED)
        elif review.decision is ReviewDecision.REJECT:
            changes["status"] = str(TicketStatus.REJECTED)
        else:
            changes["status"] = str(TicketStatus.PENDING_REVIEW)

        reference.update(changes)
        data = snapshot.to_dict()
        data.update(changes)
        return self._document_to_ticket(str(ticket_id), data)

    def list(self) -> list[Ticket]:
        from google.cloud import firestore

        documents = self._get_collection().order_by(  # type: ignore[union-attr]
            "created_at", direction=firestore.Query.DESCENDING
        ).stream()
        return [
            self._document_to_ticket(document.id, document.to_dict())
            for document in documents
        ]


def create_ticket_repository(db: Session | None = None) -> TicketDataRepository:
    """Return the configured repository without exposing credentials."""
    if settings.is_firestore:
        return FirestoreTicketRepository()
    if db is None:
        raise RuntimeError("Se requiere una sesión SQLAlchemy para SQLite.")
    return TicketRepository(db)
