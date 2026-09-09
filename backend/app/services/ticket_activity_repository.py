"""Storage-agnostic audit trail for ticket workflow events."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.ticket_activity import TicketActivity
from app.models.ticket_activity_record import TicketActivityRecord


class TicketActivityDataRepository(Protocol):
    def record(self, ticket_id: UUID, production_id: UUID | None, actor_uid: str, actor_name: str | None, action: str, detail: str | None = None) -> TicketActivity: ...
    def list_for_ticket(self, ticket_id: UUID, production_id: UUID | None) -> list[TicketActivity]: ...


def _to_activity(record: TicketActivityRecord) -> TicketActivity:
    return TicketActivity(id=UUID(record.id), ticket_id=UUID(record.ticket_id), production_id=UUID(record.production_id) if record.production_id else None, actor_uid=record.actor_uid, actor_name=record.actor_name, action=record.action, detail=record.detail, created_at=record.created_at)


class TicketActivityRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def record(self, ticket_id: UUID, production_id: UUID | None, actor_uid: str, actor_name: str | None, action: str, detail: str | None = None) -> TicketActivity:
        record = TicketActivityRecord(id=str(uuid4()), ticket_id=str(ticket_id), production_id=str(production_id) if production_id else None, actor_uid=actor_uid, actor_name=actor_name, action=action, detail=detail, created_at=datetime.now(timezone.utc))
        self._db.add(record)
        self._db.commit()
        return _to_activity(record)

    def list_for_ticket(self, ticket_id: UUID, production_id: UUID | None) -> list[TicketActivity]:
        query = self._db.query(TicketActivityRecord).filter_by(ticket_id=str(ticket_id))
        if production_id:
            query = query.filter_by(production_id=str(production_id))
        return [_to_activity(item) for item in query.order_by(TicketActivityRecord.created_at.desc()).all()]


class FirestoreTicketActivityRepository:
    def __init__(self, client: object | None = None, collection_name: str = "ticket_activity") -> None:
        self._client, self._collection_name = client, collection_name

    def _collection(self) -> object:
        if self._client is None:
            from google.cloud import firestore
            self._client = firestore.Client(project=settings.google_cloud_project, database=settings.firestore_database_id)
        return self._client.collection(self._collection_name)  # type: ignore[union-attr,no-any-return]

    @staticmethod
    def _from_data(document_id: str, data: dict[str, object]) -> TicketActivity:
        return TicketActivity(id=UUID(document_id), ticket_id=UUID(str(data["ticket_id"])), production_id=UUID(str(data["production_id"])) if data.get("production_id") else None, actor_uid=str(data["actor_uid"]), actor_name=data.get("actor_name"), action=str(data["action"]), detail=data.get("detail"), created_at=data["created_at"])  # type: ignore[arg-type]

    def record(self, ticket_id: UUID, production_id: UUID | None, actor_uid: str, actor_name: str | None, action: str, detail: str | None = None) -> TicketActivity:
        activity_id, now = uuid4(), datetime.now(timezone.utc)
        data: dict[str, object] = {"ticket_id": str(ticket_id), "production_id": str(production_id) if production_id else None, "actor_uid": actor_uid, "actor_name": actor_name, "action": action, "detail": detail, "created_at": now}
        self._collection().document(str(activity_id)).set(data)  # type: ignore[union-attr]
        return self._from_data(str(activity_id), data)

    def list_for_ticket(self, ticket_id: UUID, production_id: UUID | None) -> list[TicketActivity]:
        documents = self._collection().where("ticket_id", "==", str(ticket_id)).stream()  # type: ignore[union-attr]
        activities = [self._from_data(document.id, document.to_dict()) for document in documents if not production_id or document.to_dict().get("production_id") == str(production_id)]
        return sorted(activities, key=lambda item: item.created_at, reverse=True)


def create_ticket_activity_repository(db: Session | None = None) -> TicketActivityDataRepository:
    if settings.is_firestore:
        return FirestoreTicketActivityRepository()
    if db is None:
        raise RuntimeError("A SQLAlchemy session is required for SQLite.")
    return TicketActivityRepository(db)
