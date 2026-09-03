"""Storage-agnostic repository for private in-app notifications."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.notification import Notification, NotificationType
from app.models.notification_record import NotificationRecord


class NotificationNotFoundError(Exception):
    pass


class NotificationDataRepository(Protocol):
    def create(self, recipient_uid: str, kind: NotificationType, title: str, message: str, production_id: UUID | None = None, ticket_id: UUID | None = None) -> Notification: ...
    def list_for_user(self, user_id: str) -> list[Notification]: ...
    def mark_read(self, notification_id: UUID, user_id: str) -> Notification: ...
    def mark_all_read(self, user_id: str) -> None: ...


def _to_notification(record: NotificationRecord) -> Notification:
    return Notification(id=UUID(record.id), recipient_uid=record.recipient_uid, type=record.type, title=record.title, message=record.message, production_id=UUID(record.production_id) if record.production_id else None, ticket_id=UUID(record.ticket_id) if record.ticket_id else None, created_at=record.created_at, read_at=record.read_at)


class NotificationRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def create(self, recipient_uid: str, kind: NotificationType, title: str, message: str, production_id: UUID | None = None, ticket_id: UUID | None = None) -> Notification:
        record = NotificationRecord(id=str(uuid4()), recipient_uid=recipient_uid, type=str(kind), title=title, message=message, production_id=str(production_id) if production_id else None, ticket_id=str(ticket_id) if ticket_id else None, created_at=datetime.now(timezone.utc), read_at=None)
        self._db.add(record)
        self._db.commit()
        return _to_notification(record)

    def list_for_user(self, user_id: str) -> list[Notification]:
        rows = self._db.query(NotificationRecord).filter_by(recipient_uid=user_id).order_by(NotificationRecord.created_at.desc()).limit(50).all()
        return [_to_notification(row) for row in rows]

    def mark_read(self, notification_id: UUID, user_id: str) -> Notification:
        record = self._db.query(NotificationRecord).filter_by(id=str(notification_id), recipient_uid=user_id).one_or_none()
        if record is None:
            raise NotificationNotFoundError()
        if record.read_at is None:
            record.read_at = datetime.now(timezone.utc)
            self._db.commit()
        return _to_notification(record)

    def mark_all_read(self, user_id: str) -> None:
        self._db.query(NotificationRecord).filter_by(recipient_uid=user_id, read_at=None).update({NotificationRecord.read_at: datetime.now(timezone.utc)})
        self._db.commit()


class FirestoreNotificationRepository:
    def __init__(self, client: object | None = None, collection_name: str = "notifications") -> None:
        self._client, self._collection_name = client, collection_name

    def _collection(self) -> object:
        if self._client is None:
            from google.cloud import firestore
            self._client = firestore.Client(project=settings.google_cloud_project, database=settings.firestore_database_id)
        return self._client.collection(self._collection_name)  # type: ignore[union-attr,no-any-return]

    @staticmethod
    def _from_data(document_id: str, data: dict[str, object]) -> Notification:
        return Notification(id=UUID(document_id), recipient_uid=str(data["recipient_uid"]), type=str(data["type"]), title=str(data["title"]), message=str(data["message"]), production_id=UUID(str(data["production_id"])) if data.get("production_id") else None, ticket_id=UUID(str(data["ticket_id"])) if data.get("ticket_id") else None, created_at=data["created_at"], read_at=data.get("read_at"))  # type: ignore[arg-type]

    def create(self, recipient_uid: str, kind: NotificationType, title: str, message: str, production_id: UUID | None = None, ticket_id: UUID | None = None) -> Notification:
        notification_id, now = uuid4(), datetime.now(timezone.utc)
        data: dict[str, object] = {"recipient_uid": recipient_uid, "type": str(kind), "title": title, "message": message, "production_id": str(production_id) if production_id else None, "ticket_id": str(ticket_id) if ticket_id else None, "created_at": now, "read_at": None}
        self._collection().document(str(notification_id)).set(data)  # type: ignore[union-attr]
        return self._from_data(str(notification_id), data)

    def list_for_user(self, user_id: str) -> list[Notification]:
        documents = self._collection().where("recipient_uid", "==", user_id).stream()  # type: ignore[union-attr]
        return sorted([self._from_data(document.id, document.to_dict()) for document in documents], key=lambda item: item.created_at, reverse=True)[:50]

    def mark_read(self, notification_id: UUID, user_id: str) -> Notification:
        reference = self._collection().document(str(notification_id))  # type: ignore[union-attr]
        snapshot = reference.get()
        if not snapshot.exists or snapshot.to_dict().get("recipient_uid") != user_id:
            raise NotificationNotFoundError()
        data = snapshot.to_dict()
        if not data.get("read_at"):
            data["read_at"] = datetime.now(timezone.utc)
            reference.update({"read_at": data["read_at"]})
        return self._from_data(str(notification_id), data)

    def mark_all_read(self, user_id: str) -> None:
        for document in self._collection().where("recipient_uid", "==", user_id).stream():  # type: ignore[union-attr]
            if not document.to_dict().get("read_at"):
                document.reference.update({"read_at": datetime.now(timezone.utc)})


def create_notification_repository(db: Session | None = None) -> NotificationDataRepository:
    if settings.is_firestore:
        return FirestoreNotificationRepository()
    if db is None:
        raise RuntimeError("Se requiere una sesión SQLAlchemy para SQLite.")
    return NotificationRepository(db)
