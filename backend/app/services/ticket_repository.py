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
from app.models.ticket import (
    ArtistWorkStatus,
    QualityDecision,
    ReviewDecision,
    Ticket,
    TicketCreate,
    TicketQualityReview,
    TicketReview,
    TicketStatus,
    TicketWorkUpdate,
)
from app.models.ticket_record import TicketRecord


class TicketNotFoundError(Exception):
    """The requested ticket does not exist in the database."""


class TicketTransitionError(Exception):
    """An actor tried to apply a workflow transition that is not allowed."""


class TicketDataRepository(Protocol):
    """Common persistence operations exposed to FastAPI endpoints."""

    def create(self, payload: TicketCreate, owner_id: str = "local-supervisor", production_id: UUID | None = None) -> Ticket: ...

    def review(self, ticket_id: UUID, review: TicketReview, owner_id: str = "local-supervisor", production_id: UUID | None = None) -> Ticket: ...

    def list(self, owner_id: str = "local-supervisor", production_id: UUID | None = None) -> list[Ticket]: ...

    def update_work(self, ticket_id: UUID, update: TicketWorkUpdate, owner_id: str = "local-supervisor", production_id: UUID | None = None) -> Ticket: ...

    def attach_evidence(self, ticket_id: UUID, gs_uri: str, name: str, content_type: str, owner_id: str = "local-supervisor", production_id: UUID | None = None) -> Ticket: ...

    def clear_evidence(self, ticket_id: UUID, owner_id: str = "local-supervisor", production_id: UUID | None = None) -> Ticket: ...

    def clear_delivery_link(self, ticket_id: UUID, owner_id: str = "local-supervisor", production_id: UUID | None = None) -> Ticket: ...

    def quality_review(self, ticket_id: UUID, review: TicketQualityReview, owner_id: str = "local-supervisor", production_id: UUID | None = None) -> Ticket: ...

    def unassign_member_tasks(self, production_id: UUID, member_uid: str) -> int: ...


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
        artist_note=record.artist_note,
        delivery_link=record.delivery_link,
        evidence_gcs_uri=record.evidence_gcs_uri,
        evidence_name=record.evidence_name,
        evidence_content_type=record.evidence_content_type,
        supervisor_feedback=record.supervisor_feedback,
        production_id=UUID(record.production_id) if record.production_id else None,
        assigned_to_uid=record.assigned_to_uid,
        assigned_to_name=record.assigned_to_name,
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

    def create(self, payload: TicketCreate, owner_id: str = "local-supervisor", production_id: UUID | None = None) -> Ticket:
        """Insert a new ticket and return the Pydantic representation."""
        from uuid import uuid4

        now = datetime.now(timezone.utc)
        record = TicketRecord(
            id=str(uuid4()),
            owner_id=owner_id,
            production_id=str(production_id) if production_id else None,
            assigned_to_uid=None,
            assigned_to_name=None,
            shot_id=payload.shot_id,
            director_note=payload.director_note,
            department=str(payload.department),
            priority=str(payload.priority),
            status=str(TicketStatus.PENDING_REVIEW),
            ai_rationale=payload.ai_rationale,
            supervisor_note=None,
            artist_note=None,
            delivery_link=None,
            evidence_gcs_uri=None,
            evidence_name=None,
            evidence_content_type=None,
            supervisor_feedback=None,
            created_at=now,
            updated_at=now,
        )
        self._db.add(record)
        self._db.commit()
        self._db.refresh(record)
        return _record_to_ticket(record)

    def review(self, ticket_id: UUID, review: TicketReview, owner_id: str = "local-supervisor", production_id: UUID | None = None) -> Ticket:
        """Apply a supervisor review decision and return the updated ticket."""
        record: TicketRecord | None = self._db.get(TicketRecord, str(ticket_id))
        if record is None or not self._can_access(record, owner_id, production_id):
            raise TicketNotFoundError(f"Ticket {ticket_id} not found")

        if review.department is not None:
            record.department = str(review.department)
        if review.priority is not None:
            record.priority = str(review.priority)
        if review.supervisor_note is not None:
            record.supervisor_note = review.supervisor_note
        if review.assigned_to_uid is not None:
            record.assigned_to_uid = review.assigned_to_uid
            record.assigned_to_name = review.assigned_to_name

        if review.decision is ReviewDecision.APPROVE:
            record.status = str(TicketStatus.ASSIGNED)
        elif review.decision is ReviewDecision.REJECT:
            record.status = str(TicketStatus.REJECTED)
        else:
            record.status = str(TicketStatus.PENDING_REVIEW)

        record.updated_at = datetime.now(timezone.utc)
        self._db.commit()
        self._db.refresh(record)
        return _record_to_ticket(record)

    def update_work(self, ticket_id: UUID, update: TicketWorkUpdate, owner_id: str = "local-supervisor", production_id: UUID | None = None) -> Ticket:
        record: TicketRecord | None = self._db.get(TicketRecord, str(ticket_id))
        if record is None or not self._can_access(record, owner_id, production_id):
            raise TicketNotFoundError(f"Ticket {ticket_id} not found")

        current = TicketStatus(record.status)
        if update.status is ArtistWorkStatus.IN_PROGRESS:
            if current not in {TicketStatus.ASSIGNED, TicketStatus.APPROVED, TicketStatus.IN_PROGRESS}:
                raise TicketTransitionError("El ticket no está disponible para iniciar trabajo.")
        elif current is not TicketStatus.IN_PROGRESS:
            raise TicketTransitionError("Solo una tarea en proceso puede enviarse a control de calidad.")

        record.status = str(update.status)
        if update.artist_note is not None:
            record.artist_note = update.artist_note
        if update.delivery_link is not None:
            record.delivery_link = update.delivery_link
        record.updated_at = datetime.now(timezone.utc)
        self._db.commit()
        self._db.refresh(record)
        return _record_to_ticket(record)

    def attach_evidence(self, ticket_id: UUID, gs_uri: str, name: str, content_type: str, owner_id: str = "local-supervisor", production_id: UUID | None = None) -> Ticket:
        record: TicketRecord | None = self._db.get(TicketRecord, str(ticket_id))
        if record is None or not self._can_access(record, owner_id, production_id):
            raise TicketNotFoundError(f"Ticket {ticket_id} not found")
        if TicketStatus(record.status) is not TicketStatus.IN_PROGRESS:
            raise TicketTransitionError("Solo una tarea en proceso puede recibir evidencia.")
        record.evidence_gcs_uri = gs_uri
        record.evidence_name = name
        record.evidence_content_type = content_type
        record.updated_at = datetime.now(timezone.utc)
        self._db.commit()
        self._db.refresh(record)
        return _record_to_ticket(record)

    def clear_evidence(self, ticket_id: UUID, owner_id: str = "local-supervisor", production_id: UUID | None = None) -> Ticket:
        record: TicketRecord | None = self._db.get(TicketRecord, str(ticket_id))
        if record is None or not self._can_access(record, owner_id, production_id):
            raise TicketNotFoundError(f"Ticket {ticket_id} not found")
        if TicketStatus(record.status) is not TicketStatus.IN_PROGRESS:
            raise TicketTransitionError("Solo se puede quitar evidencia de una tarea en proceso.")
        record.evidence_gcs_uri = None
        record.evidence_name = None
        record.evidence_content_type = None
        record.updated_at = datetime.now(timezone.utc)
        self._db.commit()
        self._db.refresh(record)
        return _record_to_ticket(record)

    def clear_delivery_link(self, ticket_id: UUID, owner_id: str = "local-supervisor", production_id: UUID | None = None) -> Ticket:
        record: TicketRecord | None = self._db.get(TicketRecord, str(ticket_id))
        if record is None or not self._can_access(record, owner_id, production_id):
            raise TicketNotFoundError(f"Ticket {ticket_id} not found")
        if TicketStatus(record.status) is not TicketStatus.IN_PROGRESS:
            raise TicketTransitionError("Solo se puede quitar el enlace de una tarea en proceso.")
        record.delivery_link = None
        record.updated_at = datetime.now(timezone.utc)
        self._db.commit()
        self._db.refresh(record)
        return _record_to_ticket(record)

    def quality_review(self, ticket_id: UUID, review: TicketQualityReview, owner_id: str = "local-supervisor", production_id: UUID | None = None) -> Ticket:
        record: TicketRecord | None = self._db.get(TicketRecord, str(ticket_id))
        if record is None or not self._can_access(record, owner_id, production_id):
            raise TicketNotFoundError(f"Ticket {ticket_id} not found")
        if TicketStatus(record.status) is not TicketStatus.READY_FOR_QC:
            raise TicketTransitionError("El ticket debe estar listo para revisión de calidad.")

        record.status = str(
            TicketStatus.COMPLETED if review.decision is QualityDecision.APPROVE else TicketStatus.IN_PROGRESS
        )
        if review.supervisor_feedback is not None:
            record.supervisor_feedback = review.supervisor_feedback
        record.updated_at = datetime.now(timezone.utc)
        self._db.commit()
        self._db.refresh(record)
        return _record_to_ticket(record)

    def unassign_member_tasks(self, production_id: UUID, member_uid: str) -> int:
        """Return active work to supervisor review after an artist leaves a production."""
        active_statuses = [str(TicketStatus.ASSIGNED), str(TicketStatus.APPROVED), str(TicketStatus.IN_PROGRESS), str(TicketStatus.READY_FOR_QC)]
        count = self._db.query(TicketRecord).filter(
            TicketRecord.production_id == str(production_id),
            TicketRecord.assigned_to_uid == member_uid,
            TicketRecord.status.in_(active_statuses),
        ).update({
            TicketRecord.status: str(TicketStatus.PENDING_REVIEW),
            TicketRecord.assigned_to_uid: None,
            TicketRecord.assigned_to_name: None,
            TicketRecord.artist_note: None,
            TicketRecord.delivery_link: None,
            TicketRecord.evidence_gcs_uri: None,
            TicketRecord.evidence_name: None,
            TicketRecord.evidence_content_type: None,
            TicketRecord.supervisor_feedback: None,
            TicketRecord.updated_at: datetime.now(timezone.utc),
        }, synchronize_session=False)
        self._db.commit()
        return count

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def list(self, owner_id: str = "local-supervisor", production_id: UUID | None = None) -> list[Ticket]:
        """Return all tickets ordered by creation date descending."""
        query = self._db.query(TicketRecord)
        query = (
            query.filter(TicketRecord.production_id == str(production_id))
            if production_id
            else query.filter(
                TicketRecord.production_id.is_(None), TicketRecord.owner_id == owner_id
            )
        )
        records = query.order_by(TicketRecord.created_at.desc()).all()
        return [_record_to_ticket(r) for r in records]

    @staticmethod
    def _can_access(record: TicketRecord, owner_id: str, production_id: UUID | None) -> bool:
        """Scope production work strictly; legacy tickets remain private."""
        if production_id:
            return record.production_id == str(production_id)
        return record.production_id is None and record.owner_id == owner_id


class FirestoreTicketRepository:
    """Firestore-backed ticket repository authenticated through ADC."""

    def __init__(self, client: object | None = None, collection_name: str | None = None) -> None:
        settings.validate_ticket_storage()
        self._client = client
        self._collection_name = collection_name or settings.firestore_collection

    def _get_client(self) -> object:
        if self._client is None:
            from google.cloud import firestore

            self._client = firestore.Client(
                project=settings.google_cloud_project,
                database=settings.firestore_database_id,
            )
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
            artist_note=data.get("artist_note"),  # type: ignore[arg-type]
            delivery_link=data.get("delivery_link"),  # type: ignore[arg-type]
            evidence_gcs_uri=data.get("evidence_gcs_uri"),  # type: ignore[arg-type]
            evidence_name=data.get("evidence_name"),  # type: ignore[arg-type]
            evidence_content_type=data.get("evidence_content_type"),  # type: ignore[arg-type]
            supervisor_feedback=data.get("supervisor_feedback"),  # type: ignore[arg-type]
            production_id=UUID(str(data["production_id"])) if data.get("production_id") else None,
            assigned_to_uid=data.get("assigned_to_uid"),  # type: ignore[arg-type]
            assigned_to_name=data.get("assigned_to_name"),  # type: ignore[arg-type]
            created_at=data["created_at"],  # type: ignore[arg-type]
            updated_at=data["updated_at"],  # type: ignore[arg-type]
        )

    def create(self, payload: TicketCreate, owner_id: str = "local-supervisor", production_id: UUID | None = None) -> Ticket:
        from uuid import uuid4

        ticket_id = uuid4()
        now = datetime.now(timezone.utc)
        data: dict[str, object] = {
            "owner_id": owner_id,
            "production_id": str(production_id) if production_id else None,
            "assigned_to_uid": None,
            "assigned_to_name": None,
            "shot_id": payload.shot_id,
            "director_note": payload.director_note,
            "department": str(payload.department),
            "priority": str(payload.priority),
            "status": str(TicketStatus.PENDING_REVIEW),
            "ai_rationale": payload.ai_rationale,
            "supervisor_note": None,
            "artist_note": None,
            "delivery_link": None,
            "evidence_gcs_uri": None,
            "evidence_name": None,
            "evidence_content_type": None,
            "supervisor_feedback": None,
            "created_at": now,
            "updated_at": now,
        }
        self._get_collection().document(str(ticket_id)).set(data)  # type: ignore[union-attr]
        return self._document_to_ticket(str(ticket_id), data)

    def review(self, ticket_id: UUID, review: TicketReview, owner_id: str = "local-supervisor", production_id: UUID | None = None) -> Ticket:
        reference = self._get_collection().document(str(ticket_id))  # type: ignore[union-attr]
        snapshot = reference.get()
        if not snapshot.exists or not self._can_access(snapshot.to_dict(), owner_id, production_id):
            raise TicketNotFoundError(f"Ticket {ticket_id} not found")

        changes: dict[str, object] = {"updated_at": datetime.now(timezone.utc)}
        if review.department is not None:
            changes["department"] = str(review.department)
        if review.priority is not None:
            changes["priority"] = str(review.priority)
        if review.supervisor_note is not None:
            changes["supervisor_note"] = review.supervisor_note
        if review.assigned_to_uid is not None:
            changes["assigned_to_uid"] = review.assigned_to_uid
            changes["assigned_to_name"] = review.assigned_to_name

        if review.decision is ReviewDecision.APPROVE:
            changes["status"] = str(TicketStatus.ASSIGNED)
        elif review.decision is ReviewDecision.REJECT:
            changes["status"] = str(TicketStatus.REJECTED)
        else:
            changes["status"] = str(TicketStatus.PENDING_REVIEW)

        reference.update(changes)
        data = snapshot.to_dict()
        data.update(changes)
        return self._document_to_ticket(str(ticket_id), data)

    def update_work(self, ticket_id: UUID, update: TicketWorkUpdate, owner_id: str = "local-supervisor", production_id: UUID | None = None) -> Ticket:
        reference = self._get_collection().document(str(ticket_id))  # type: ignore[union-attr]
        snapshot = reference.get()
        if not snapshot.exists or not self._can_access(snapshot.to_dict(), owner_id, production_id):
            raise TicketNotFoundError(f"Ticket {ticket_id} not found")

        data = snapshot.to_dict()
        current = TicketStatus(str(data["status"]))
        if update.status is ArtistWorkStatus.IN_PROGRESS:
            if current not in {TicketStatus.ASSIGNED, TicketStatus.APPROVED, TicketStatus.IN_PROGRESS}:
                raise TicketTransitionError("El ticket no está disponible para iniciar trabajo.")
        elif current is not TicketStatus.IN_PROGRESS:
            raise TicketTransitionError("Solo una tarea en proceso puede enviarse a control de calidad.")

        changes: dict[str, object] = {"status": str(update.status), "updated_at": datetime.now(timezone.utc)}
        if update.artist_note is not None:
            changes["artist_note"] = update.artist_note
        if update.delivery_link is not None:
            changes["delivery_link"] = update.delivery_link
        reference.update(changes)
        data.update(changes)
        return self._document_to_ticket(str(ticket_id), data)

    def attach_evidence(self, ticket_id: UUID, gs_uri: str, name: str, content_type: str, owner_id: str = "local-supervisor", production_id: UUID | None = None) -> Ticket:
        reference = self._get_collection().document(str(ticket_id))  # type: ignore[union-attr]
        snapshot = reference.get()
        if not snapshot.exists or not self._can_access(snapshot.to_dict(), owner_id, production_id):
            raise TicketNotFoundError(f"Ticket {ticket_id} not found")
        data = snapshot.to_dict()
        if TicketStatus(str(data["status"])) is not TicketStatus.IN_PROGRESS:
            raise TicketTransitionError("Solo una tarea en proceso puede recibir evidencia.")
        changes: dict[str, object] = {
            "evidence_gcs_uri": gs_uri,
            "evidence_name": name,
            "evidence_content_type": content_type,
            "updated_at": datetime.now(timezone.utc),
        }
        reference.update(changes)
        data.update(changes)
        return self._document_to_ticket(str(ticket_id), data)

    def clear_evidence(self, ticket_id: UUID, owner_id: str = "local-supervisor", production_id: UUID | None = None) -> Ticket:
        reference = self._get_collection().document(str(ticket_id))  # type: ignore[union-attr]
        snapshot = reference.get()
        if not snapshot.exists or not self._can_access(snapshot.to_dict(), owner_id, production_id):
            raise TicketNotFoundError(f"Ticket {ticket_id} not found")
        data = snapshot.to_dict()
        if TicketStatus(str(data["status"])) is not TicketStatus.IN_PROGRESS:
            raise TicketTransitionError("Solo se puede quitar evidencia de una tarea en proceso.")
        changes: dict[str, object] = {
            "evidence_gcs_uri": None,
            "evidence_name": None,
            "evidence_content_type": None,
            "updated_at": datetime.now(timezone.utc),
        }
        reference.update(changes)
        data.update(changes)
        return self._document_to_ticket(str(ticket_id), data)

    def clear_delivery_link(self, ticket_id: UUID, owner_id: str = "local-supervisor", production_id: UUID | None = None) -> Ticket:
        reference = self._get_collection().document(str(ticket_id))  # type: ignore[union-attr]
        snapshot = reference.get()
        if not snapshot.exists or not self._can_access(snapshot.to_dict(), owner_id, production_id):
            raise TicketNotFoundError(f"Ticket {ticket_id} not found")
        data = snapshot.to_dict()
        if TicketStatus(str(data["status"])) is not TicketStatus.IN_PROGRESS:
            raise TicketTransitionError("Solo se puede quitar el enlace de una tarea en proceso.")
        changes: dict[str, object] = {"delivery_link": None, "updated_at": datetime.now(timezone.utc)}
        reference.update(changes)
        data.update(changes)
        return self._document_to_ticket(str(ticket_id), data)

    def quality_review(self, ticket_id: UUID, review: TicketQualityReview, owner_id: str = "local-supervisor", production_id: UUID | None = None) -> Ticket:
        reference = self._get_collection().document(str(ticket_id))  # type: ignore[union-attr]
        snapshot = reference.get()
        if not snapshot.exists or not self._can_access(snapshot.to_dict(), owner_id, production_id):
            raise TicketNotFoundError(f"Ticket {ticket_id} not found")
        data = snapshot.to_dict()
        if TicketStatus(str(data["status"])) is not TicketStatus.READY_FOR_QC:
            raise TicketTransitionError("El ticket debe estar listo para revisión de calidad.")

        changes: dict[str, object] = {
            "status": str(TicketStatus.COMPLETED if review.decision is QualityDecision.APPROVE else TicketStatus.IN_PROGRESS),
            "updated_at": datetime.now(timezone.utc),
        }
        if review.supervisor_feedback is not None:
            changes["supervisor_feedback"] = review.supervisor_feedback
        reference.update(changes)
        data.update(changes)
        return self._document_to_ticket(str(ticket_id), data)

    def unassign_member_tasks(self, production_id: UUID, member_uid: str) -> int:
        active_statuses = {str(TicketStatus.ASSIGNED), str(TicketStatus.APPROVED), str(TicketStatus.IN_PROGRESS), str(TicketStatus.READY_FOR_QC)}
        count = 0
        for document in self._get_collection().where("production_id", "==", str(production_id)).stream():  # type: ignore[union-attr]
            data = document.to_dict()
            if data.get("assigned_to_uid") != member_uid or data.get("status") not in active_statuses:
                continue
            document.reference.update({
                "status": str(TicketStatus.PENDING_REVIEW),
                "assigned_to_uid": None,
                "assigned_to_name": None,
                "artist_note": None,
                "delivery_link": None,
                "evidence_gcs_uri": None,
                "evidence_name": None,
                "evidence_content_type": None,
                "supervisor_feedback": None,
                "updated_at": datetime.now(timezone.utc),
            })
            count += 1
        return count

    def list(self, owner_id: str = "local-supervisor", production_id: UUID | None = None) -> list[Ticket]:
        # Sort in Python to avoid requiring a composite Firestore index for a
        # first deployment. The collection is per-user and small in this demo.
        collection = self._get_collection()
        if production_id:
            documents = collection.where("production_id", "==", str(production_id)).stream()  # type: ignore[union-attr]
        else:
            documents = collection.where("owner_id", "==", owner_id).stream()  # type: ignore[union-attr]
        tickets = [
            self._document_to_ticket(document.id, document.to_dict())
            for document in {document.id: document for document in documents}.values()
            if self._can_access(document.to_dict(), owner_id, production_id)
        ]
        return sorted(tickets, key=lambda ticket: ticket.created_at, reverse=True)

    @staticmethod
    def _can_access(data: dict[str, object], owner_id: str, production_id: UUID | None) -> bool:
        value = data.get("production_id")
        if production_id:
            return value == str(production_id)
        return value is None and data.get("owner_id") == owner_id


def create_ticket_repository(db: Session | None = None) -> TicketDataRepository:
    """Return the configured repository without exposing credentials."""
    if settings.is_firestore:
        return FirestoreTicketRepository()
    if db is None:
        raise RuntimeError("Se requiere una sesión SQLAlchemy para SQLite.")
    return TicketRepository(db)
