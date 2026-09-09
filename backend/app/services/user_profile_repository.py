"""Storage-agnostic persistence for authenticated FrameFlow profiles."""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from typing import Protocol

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import CurrentUser
from app.models.user_profile import UserProfile, UserProfileUpdate
from app.models.user_profile_record import UserProfileRecord

_USERNAME_RE = re.compile(r"^[a-z0-9](?:[a-z0-9._-]{1,28}[a-z0-9])?$")
_FIREBASE_UID_RE = re.compile(r"^[A-Za-z0-9_-]{20,128}$")


class ProfileNotFoundError(Exception):
    pass


class UsernameUnavailableError(Exception):
    pass


class InvalidUsernameError(Exception):
    pass


def is_valid_firebase_uid(value: str) -> bool:
    """Accept the generated Firebase UID shape used by FrameFlow accounts."""
    return bool(_FIREBASE_UID_RE.fullmatch(value.strip()))


class UserProfileDataRepository(Protocol):
    def ensure(self, user: CurrentUser) -> UserProfile: ...
    def get(self, uid: str) -> UserProfile | None: ...
    def search(self, query: str, exclude_uid: str, limit: int = 8) -> list[UserProfile]: ...
    def update(self, uid: str, payload: UserProfileUpdate) -> UserProfile: ...
    def set_avatar(self, uid: str, gs_uri: str) -> tuple[UserProfile, str | None]: ...
    def clear_avatar(self, uid: str) -> tuple[UserProfile, str | None]: ...
    def avatar_uri(self, uid: str) -> str | None: ...


def normalize_username(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.strip().lower().lstrip("@"))
    value = "".join(character for character in value if not unicodedata.combining(character))
    value = re.sub(r"[^a-z0-9._-]+", "-", value)
    value = re.sub(r"[-_.]{2,}", "-", value).strip("-_.")
    return value[:30]


def validate_username(value: str) -> str:
    normalized = normalize_username(value)
    if len(normalized) < 3 or not _USERNAME_RE.fullmatch(normalized):
        raise InvalidUsernameError()
    return normalized


def _default_display_name(user: CurrentUser) -> str:
    if user.name and user.name.strip():
        return user.name.strip()[:80]
    if user.email:
        return user.email.split("@", 1)[0][:80]
    return "FrameFlow user"


def _base_username(user: CurrentUser) -> str:
    source = user.email.split("@", 1)[0] if user.email else user.name or f"user-{user.uid[-8:]}"
    normalized = normalize_username(source)
    if len(normalized) < 3:
        normalized = f"user-{user.uid[-8:].lower()}"
    return normalized[:30]


def _public_profile(*, uid: str, username: str, display_name: str, photo_url: str | None, avatar_gcs_uri: str | None, created_at: datetime, updated_at: datetime) -> UserProfile:
    return UserProfile(
        uid=uid,
        username=username,
        display_name=display_name,
        photo_url=photo_url,
        has_custom_avatar=bool(avatar_gcs_uri),
        created_at=created_at,
        updated_at=updated_at,
    )


class UserProfileRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    @staticmethod
    def _from_record(record: UserProfileRecord) -> UserProfile:
        return _public_profile(
            uid=record.uid,
            username=record.username,
            display_name=record.display_name,
            photo_url=record.photo_url,
            avatar_gcs_uri=record.avatar_gcs_uri,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    def _available_username(self, base: str, uid: str) -> str:
        candidate = base
        suffix = normalize_username(uid[-6:]) or "member"
        attempt = 0
        while self._db.query(UserProfileRecord).filter_by(username=candidate).first() is not None:
            attempt += 1
            ending = suffix if attempt == 1 else f"{suffix}{attempt}"
            candidate = f"{base[: max(3, 29 - len(ending))]}-{ending}"[:30]
        return candidate

    def ensure(self, user: CurrentUser) -> UserProfile:
        record = self._db.get(UserProfileRecord, user.uid)
        if record is None:
            now = datetime.now(timezone.utc)
            record = UserProfileRecord(
                uid=user.uid,
                username=self._available_username(_base_username(user), user.uid),
                display_name=_default_display_name(user),
                email=user.email,
                photo_url=user.photo_url,
                created_at=now,
                updated_at=now,
            )
            self._db.add(record)
            self._db.commit()
        else:
            changed = False
            if user.email and record.email != user.email:
                record.email, changed = user.email, True
            if user.photo_url and record.photo_url != user.photo_url:
                record.photo_url, changed = user.photo_url, True
            if changed:
                record.updated_at = datetime.now(timezone.utc)
                self._db.commit()
        return self._from_record(record)

    def get(self, uid: str) -> UserProfile | None:
        record = self._db.get(UserProfileRecord, uid)
        return self._from_record(record) if record else None

    def search(self, query: str, exclude_uid: str, limit: int = 8) -> list[UserProfile]:
        cleaned = query.strip().lstrip("@").lower()
        if len(cleaned) < 2:
            return []
        rows = (
            self._db.query(UserProfileRecord)
            .filter(UserProfileRecord.uid != exclude_uid)
            .filter(or_(
                UserProfileRecord.uid == query.strip(),
                func.lower(UserProfileRecord.username).like(f"{cleaned}%"),
                func.lower(UserProfileRecord.display_name).like(f"{cleaned}%"),
            ))
            .order_by(UserProfileRecord.username)
            .limit(limit)
            .all()
        )
        return [self._from_record(row) for row in rows]

    def update(self, uid: str, payload: UserProfileUpdate) -> UserProfile:
        record = self._db.get(UserProfileRecord, uid)
        if record is None:
            raise ProfileNotFoundError()
        username = validate_username(payload.username)
        duplicate = self._db.query(UserProfileRecord).filter(UserProfileRecord.username == username, UserProfileRecord.uid != uid).first()
        if duplicate:
            raise UsernameUnavailableError()
        record.username = username
        record.display_name = payload.display_name.strip()
        record.updated_at = datetime.now(timezone.utc)
        self._db.commit()
        return self._from_record(record)

    def set_avatar(self, uid: str, gs_uri: str) -> tuple[UserProfile, str | None]:
        record = self._db.get(UserProfileRecord, uid)
        if record is None:
            raise ProfileNotFoundError()
        previous = record.avatar_gcs_uri
        record.avatar_gcs_uri = gs_uri
        record.updated_at = datetime.now(timezone.utc)
        self._db.commit()
        return self._from_record(record), previous

    def clear_avatar(self, uid: str) -> tuple[UserProfile, str | None]:
        record = self._db.get(UserProfileRecord, uid)
        if record is None:
            raise ProfileNotFoundError()
        previous = record.avatar_gcs_uri
        record.avatar_gcs_uri = None
        record.updated_at = datetime.now(timezone.utc)
        self._db.commit()
        return self._from_record(record), previous

    def avatar_uri(self, uid: str) -> str | None:
        record = self._db.get(UserProfileRecord, uid)
        return record.avatar_gcs_uri if record else None


class FirestoreUserProfileRepository:
    def __init__(self, client: object | None = None, collection_name: str = "user_profiles") -> None:
        self._client = client
        self._collection_name = collection_name

    def _collection(self) -> object:
        if self._client is None:
            from google.cloud import firestore
            self._client = firestore.Client(project=settings.google_cloud_project, database=settings.firestore_database_id)
        return self._client.collection(self._collection_name)  # type: ignore[union-attr,no-any-return]

    def _handle(self, username: str) -> object:
        self._collection()
        return self._client.collection(f"{self._collection_name}_usernames").document(username)  # type: ignore[union-attr,no-any-return]

    @staticmethod
    def _from_data(uid: str, data: dict[str, object]) -> UserProfile:
        return _public_profile(
            uid=uid,
            username=str(data["username"]),
            display_name=str(data["display_name"]),
            photo_url=str(data["photo_url"]) if data.get("photo_url") else None,
            avatar_gcs_uri=str(data["avatar_gcs_uri"]) if data.get("avatar_gcs_uri") else None,
            created_at=data["created_at"],  # type: ignore[arg-type]
            updated_at=data["updated_at"],  # type: ignore[arg-type]
        )

    def _reserve_username(self, username: str, uid: str) -> None:
        from google.cloud import firestore

        reference = self._handle(username)
        transaction = self._client.transaction()  # type: ignore[union-attr]

        @firestore.transactional
        def reserve(transaction: object) -> None:
            snapshot = reference.get(transaction=transaction)  # type: ignore[union-attr]
            if snapshot.exists and snapshot.to_dict().get("uid") != uid:
                raise UsernameUnavailableError()
            transaction.set(reference, {"uid": uid})  # type: ignore[union-attr]

        reserve(transaction)

    def _available_username(self, base: str, uid: str) -> str:
        candidate = base
        suffix = normalize_username(uid[-6:]) or "member"
        attempt = 0
        while True:
            try:
                self._reserve_username(candidate, uid)
                return candidate
            except UsernameUnavailableError:
                attempt += 1
                ending = suffix if attempt == 1 else f"{suffix}{attempt}"
                candidate = f"{base[: max(3, 29 - len(ending))]}-{ending}"[:30]

    def ensure(self, user: CurrentUser) -> UserProfile:
        reference = self._collection().document(user.uid)  # type: ignore[union-attr]
        snapshot = reference.get()
        if not snapshot.exists:
            now = datetime.now(timezone.utc)
            data: dict[str, object] = {
                "username": self._available_username(_base_username(user), user.uid),
                "display_name": _default_display_name(user),
                "email": user.email,
                "photo_url": user.photo_url,
                "avatar_gcs_uri": None,
                "created_at": now,
                "updated_at": now,
            }
            reference.set(data)
            return self._from_data(user.uid, data)
        data = snapshot.to_dict()
        updates: dict[str, object] = {}
        if user.email and data.get("email") != user.email:
            updates["email"] = user.email
        if user.photo_url and data.get("photo_url") != user.photo_url:
            updates["photo_url"] = user.photo_url
        if updates:
            updates["updated_at"] = datetime.now(timezone.utc)
            reference.update(updates)
            data |= updates
        return self._from_data(user.uid, data)

    def get(self, uid: str) -> UserProfile | None:
        snapshot = self._collection().document(uid).get()  # type: ignore[union-attr]
        return self._from_data(uid, snapshot.to_dict()) if snapshot.exists else None

    def search(self, query: str, exclude_uid: str, limit: int = 8) -> list[UserProfile]:
        cleaned = query.strip().lstrip("@").lower()
        if len(cleaned) < 2:
            return []
        exact_uid = self.get(query.strip()) if is_valid_firebase_uid(query) else None
        if exact_uid and exact_uid.uid != exclude_uid:
            return [exact_uid]
        rows = (
            self._collection()
            .order_by("username")  # type: ignore[union-attr]
            .start_at({"username": cleaned})
            .end_at({"username": f"{cleaned}\uf8ff"})
            .limit(limit + 1)
            .stream()
        )
        results = [self._from_data(document.id, document.to_dict()) for document in rows if document.id != exclude_uid]
        return results[:limit]

    def update(self, uid: str, payload: UserProfileUpdate) -> UserProfile:
        reference = self._collection().document(uid)  # type: ignore[union-attr]
        snapshot = reference.get()
        if not snapshot.exists:
            raise ProfileNotFoundError()
        username = validate_username(payload.username)
        updates: dict[str, object] = {
            "username": username,
            "display_name": payload.display_name.strip(),
            "updated_at": datetime.now(timezone.utc),
        }
        from google.cloud import firestore

        new_handle = self._handle(username)
        transaction = self._client.transaction()  # type: ignore[union-attr]

        @firestore.transactional
        def update_identity(transaction: object) -> dict[str, object]:
            # Reading the profile inside the transaction prevents concurrent
            # renames from leaving orphaned username reservations behind.
            current_snapshot = reference.get(transaction=transaction)  # type: ignore[union-attr]
            if not current_snapshot.exists:
                raise ProfileNotFoundError()
            current_data = current_snapshot.to_dict()
            handle_snapshot = new_handle.get(transaction=transaction)  # type: ignore[union-attr]
            if handle_snapshot.exists and handle_snapshot.to_dict().get("uid") != uid:
                raise UsernameUnavailableError()
            transaction.set(new_handle, {"uid": uid})  # type: ignore[union-attr]
            old_username = str(current_data["username"])
            if old_username != username:
                transaction.delete(self._handle(old_username))  # type: ignore[union-attr]
            transaction.update(reference, updates)  # type: ignore[union-attr]
            return current_data

        current_data = update_identity(transaction)
        return self._from_data(uid, current_data | updates)

    def set_avatar(self, uid: str, gs_uri: str) -> tuple[UserProfile, str | None]:
        reference = self._collection().document(uid)  # type: ignore[union-attr]
        snapshot = reference.get()
        if not snapshot.exists:
            raise ProfileNotFoundError()
        data = snapshot.to_dict()
        previous = str(data["avatar_gcs_uri"]) if data.get("avatar_gcs_uri") else None
        updates: dict[str, object] = {"avatar_gcs_uri": gs_uri, "updated_at": datetime.now(timezone.utc)}
        reference.update(updates)
        return self._from_data(uid, data | updates), previous

    def clear_avatar(self, uid: str) -> tuple[UserProfile, str | None]:
        reference = self._collection().document(uid)  # type: ignore[union-attr]
        snapshot = reference.get()
        if not snapshot.exists:
            raise ProfileNotFoundError()
        data = snapshot.to_dict()
        previous = str(data["avatar_gcs_uri"]) if data.get("avatar_gcs_uri") else None
        updates: dict[str, object] = {"avatar_gcs_uri": None, "updated_at": datetime.now(timezone.utc)}
        reference.update(updates)
        return self._from_data(uid, data | updates), previous

    def avatar_uri(self, uid: str) -> str | None:
        snapshot = self._collection().document(uid).get()  # type: ignore[union-attr]
        if not snapshot.exists:
            return None
        value = snapshot.to_dict().get("avatar_gcs_uri")
        return str(value) if value else None


def create_user_profile_repository(db: Session | None = None) -> UserProfileDataRepository:
    if settings.is_firestore:
        return FirestoreUserProfileRepository(collection_name=settings.user_profile_collection)
    if db is None:
        raise RuntimeError("A SQLAlchemy session is required for SQLite.")
    return UserProfileRepository(db)
