"""Storage-agnostic persistence for the FrameFlow production/team foundation."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.production import MembershipStatus, Production, ProductionCreate, ProductionMember, ProductionMemberCreate, ProductionRole, ProductionUpdate
from app.models.production_record import ProductionMemberRecord, ProductionRecord


class ProductionNotFoundError(Exception):
    pass


class ProductionPermissionError(Exception):
    pass


class ProductionDataRepository(Protocol):
    def create(self, payload: ProductionCreate, user_id: str) -> Production: ...
    def list_for_user(self, user_id: str) -> list[Production]: ...
    def bootstrap_personal(self, user_id: str, display_name: str | None, email: str | None) -> Production: ...
    def list_members(self, production_id: UUID, user_id: str) -> list[ProductionMember]: ...
    def add_member(self, production_id: UUID, payload: ProductionMemberCreate, user_id: str) -> ProductionMember: ...
    def list_invitations(self, user_id: str) -> list[ProductionMember]: ...
    def respond_to_invitation(self, production_id: UUID, user_id: str, decision: MembershipStatus) -> ProductionMember: ...
    def update(self, production_id: UUID, payload: ProductionUpdate, user_id: str) -> Production: ...


def _to_production(record: ProductionRecord, role: str | None = None) -> Production:
    return Production(id=UUID(record.id), name=record.name, created_by=record.created_by, created_at=record.created_at, updated_at=record.updated_at, current_user_role=role)


class ProductionRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def create(self, payload: ProductionCreate, user_id: str) -> Production:
        now = datetime.now(timezone.utc)
        record = ProductionRecord(id=str(uuid4()), name=payload.name.strip(), created_by=user_id, created_at=now, updated_at=now)
        self._db.add(record)
        self._db.add(ProductionMemberRecord(production_id=record.id, uid=user_id, role=str(ProductionRole.PRODUCER), membership_status=str(MembershipStatus.ACCEPTED), created_at=now))
        self._db.commit()
        return _to_production(record, ProductionRole.PRODUCER)

    def list_for_user(self, user_id: str) -> list[Production]:
        rows = self._db.query(ProductionRecord, ProductionMemberRecord.role).join(ProductionMemberRecord, ProductionMemberRecord.production_id == ProductionRecord.id).filter(ProductionMemberRecord.uid == user_id, ProductionMemberRecord.membership_status == str(MembershipStatus.ACCEPTED)).order_by(ProductionRecord.created_at.desc()).all()
        return [_to_production(record, role) for record, role in rows]

    def bootstrap_personal(self, user_id: str, display_name: str | None, email: str | None) -> Production:
        existing = self.list_for_user(user_id)
        if existing:
            return existing[0]
        label = display_name or (email.split("@", 1)[0] if email else "Mi producción")
        return self.create(ProductionCreate(name=f"{label} · Producción"), user_id)

    def _require_role(self, production_id: UUID, user_id: str, allowed: set[ProductionRole]) -> ProductionMemberRecord:
        membership = self._db.query(ProductionMemberRecord).filter_by(production_id=str(production_id), uid=user_id).one_or_none()
        if membership is None:
            raise ProductionNotFoundError()
        if MembershipStatus(membership.membership_status) is not MembershipStatus.ACCEPTED or ProductionRole(membership.role) not in allowed:
            raise ProductionPermissionError()
        return membership

    def list_members(self, production_id: UUID, user_id: str) -> list[ProductionMember]:
        self._require_role(production_id, user_id, set(ProductionRole))
        caller = self._require_role(production_id, user_id, set(ProductionRole))
        query = self._db.query(ProductionMemberRecord).filter_by(production_id=str(production_id))
        if ProductionRole(caller.role) is not ProductionRole.PRODUCER:
            query = query.filter_by(membership_status=str(MembershipStatus.ACCEPTED))
        rows = query.order_by(ProductionMemberRecord.created_at).all()
        return [ProductionMember(production_id=production_id, uid=r.uid, role=r.role, department=r.department, display_name=r.display_name, email=r.email, created_at=r.created_at, membership_status=r.membership_status) for r in rows]

    def add_member(self, production_id: UUID, payload: ProductionMemberCreate, user_id: str) -> ProductionMember:
        self._require_role(production_id, user_id, {ProductionRole.PRODUCER})
        now = datetime.now(timezone.utc)
        row = self._db.query(ProductionMemberRecord).filter_by(production_id=str(production_id), uid=payload.uid).one_or_none()
        if row is None:
            row = ProductionMemberRecord(production_id=str(production_id), uid=payload.uid, membership_status=str(MembershipStatus.PENDING), created_at=now)
            self._db.add(row)
        elif MembershipStatus(row.membership_status) is MembershipStatus.DECLINED:
            row.membership_status = str(MembershipStatus.PENDING)
        row.role, row.department, row.display_name, row.email = str(payload.role), str(payload.department) if payload.department else None, payload.display_name, payload.email
        self._db.commit()
        return ProductionMember(production_id=production_id, uid=row.uid, role=row.role, department=row.department, display_name=row.display_name, email=row.email, created_at=row.created_at, membership_status=row.membership_status)

    def list_invitations(self, user_id: str) -> list[ProductionMember]:
        rows = self._db.query(ProductionMemberRecord, ProductionRecord.name).join(ProductionRecord, ProductionRecord.id == ProductionMemberRecord.production_id).filter(ProductionMemberRecord.uid == user_id, ProductionMemberRecord.membership_status == str(MembershipStatus.PENDING)).order_by(ProductionMemberRecord.created_at.desc()).all()
        return [ProductionMember(production_id=UUID(row.production_id), uid=row.uid, role=row.role, department=row.department, display_name=row.display_name, email=row.email, created_at=row.created_at, membership_status=row.membership_status, production_name=name) for row, name in rows]

    def respond_to_invitation(self, production_id: UUID, user_id: str, decision: MembershipStatus) -> ProductionMember:
        if decision not in {MembershipStatus.ACCEPTED, MembershipStatus.DECLINED}:
            raise ProductionPermissionError()
        row = self._db.query(ProductionMemberRecord).filter_by(production_id=str(production_id), uid=user_id, membership_status=str(MembershipStatus.PENDING)).one_or_none()
        if row is None:
            raise ProductionNotFoundError()
        row.membership_status = str(decision)
        self._db.commit()
        return ProductionMember(production_id=production_id, uid=row.uid, role=row.role, department=row.department, display_name=row.display_name, email=row.email, created_at=row.created_at, membership_status=row.membership_status)

    def update(self, production_id: UUID, payload: ProductionUpdate, user_id: str) -> Production:
        self._require_role(production_id, user_id, {ProductionRole.PRODUCER})
        record = self._db.query(ProductionRecord).filter_by(id=str(production_id)).one_or_none()
        if record is None:
            raise ProductionNotFoundError()
        record.name, record.updated_at = payload.name.strip(), datetime.now(timezone.utc)
        self._db.commit()
        return _to_production(record, ProductionRole.PRODUCER)


class FirestoreProductionRepository:
    def __init__(self, client: object | None = None, collection_name: str = "productions") -> None:
        self._client = client
        self._collection_name = collection_name

    def _collection(self) -> object:
        if self._client is None:
            from google.cloud import firestore
            self._client = firestore.Client(project=settings.google_cloud_project, database=settings.firestore_database_id)
        return self._client.collection(self._collection_name)  # type: ignore[union-attr,no-any-return]

    @staticmethod
    def _from_data(document_id: str, data: dict[str, object], role: str | None = None) -> Production:
        return Production(id=UUID(document_id), name=str(data["name"]), created_by=str(data["created_by"]), created_at=data["created_at"], updated_at=data["updated_at"], current_user_role=role)

    def create(self, payload: ProductionCreate, user_id: str) -> Production:
        now, production_id = datetime.now(timezone.utc), str(uuid4())
        data: dict[str, object] = {"name": payload.name.strip(), "created_by": user_id, "created_at": now, "updated_at": now}
        reference = self._collection().document(production_id)  # type: ignore[union-attr]
        reference.set(data)
        reference.collection("members").document(user_id).set({"uid": user_id, "role": str(ProductionRole.PRODUCER), "department": None, "display_name": None, "email": None, "membership_status": str(MembershipStatus.ACCEPTED), "created_at": now})
        return self._from_data(production_id, data, ProductionRole.PRODUCER)

    def list_for_user(self, user_id: str) -> list[Production]:
        # Small hackathon data set: avoid a collection-group index by checking members per production.
        results: list[Production] = []
        for document in self._collection().stream():  # type: ignore[union-attr]
            member = document.reference.collection("members").document(user_id).get()
            if member.exists and member.to_dict().get("membership_status", MembershipStatus.ACCEPTED) == MembershipStatus.ACCEPTED:
                results.append(self._from_data(document.id, document.to_dict(), member.to_dict()["role"]))
        return sorted(results, key=lambda production: production.created_at, reverse=True)

    def bootstrap_personal(self, user_id: str, display_name: str | None, email: str | None) -> Production:
        existing = self.list_for_user(user_id)
        if existing:
            return existing[0]
        label = display_name or (email.split("@", 1)[0] if email else "Mi producción")
        return self.create(ProductionCreate(name=f"{label} · Producción"), user_id)

    def _member(self, production_id: UUID, user_id: str) -> object:
        reference = self._collection().document(str(production_id))  # type: ignore[union-attr]
        if not reference.get().exists:
            raise ProductionNotFoundError()
        member = reference.collection("members").document(user_id).get()
        if not member.exists or member.to_dict().get("membership_status", MembershipStatus.ACCEPTED) != MembershipStatus.ACCEPTED:
            raise ProductionNotFoundError()
        return member

    def list_members(self, production_id: UUID, user_id: str) -> list[ProductionMember]:
        self._member(production_id, user_id)
        caller = self._member(production_id, user_id)
        rows = self._collection().document(str(production_id)).collection("members").stream()  # type: ignore[union-attr]
        if caller.to_dict()["role"] != ProductionRole.PRODUCER:
            rows = [row for row in rows if row.to_dict().get("membership_status", MembershipStatus.ACCEPTED) == MembershipStatus.ACCEPTED]
        return [ProductionMember(production_id=production_id, **row.to_dict()) for row in rows]

    def add_member(self, production_id: UUID, payload: ProductionMemberCreate, user_id: str) -> ProductionMember:
        caller = self._member(production_id, user_id)
        if caller.to_dict()["role"] != ProductionRole.PRODUCER:
            raise ProductionPermissionError()
        now = datetime.now(timezone.utc)
        member_reference = self._collection().document(str(production_id)).collection("members").document(payload.uid)  # type: ignore[union-attr]
        existing = member_reference.get()
        existing_status = existing.to_dict().get("membership_status", MembershipStatus.ACCEPTED) if existing.exists else None
        membership_status = MembershipStatus.PENDING if not existing.exists or existing_status == MembershipStatus.DECLINED else existing_status
        data = payload.model_dump(mode="json") | {"created_at": now, "membership_status": membership_status}
        member_reference.set(data)
        return ProductionMember(production_id=production_id, **data)

    def list_invitations(self, user_id: str) -> list[ProductionMember]:
        invitations: list[ProductionMember] = []
        for document in self._collection().stream():  # type: ignore[union-attr]
            member = document.reference.collection("members").document(user_id).get()
            if member.exists and member.to_dict().get("membership_status") == MembershipStatus.PENDING:
                invitations.append(ProductionMember(production_id=UUID(document.id), production_name=document.to_dict()["name"], **member.to_dict()))
        return sorted(invitations, key=lambda invitation: invitation.created_at, reverse=True)

    def respond_to_invitation(self, production_id: UUID, user_id: str, decision: MembershipStatus) -> ProductionMember:
        if decision not in {MembershipStatus.ACCEPTED, MembershipStatus.DECLINED}:
            raise ProductionPermissionError()
        member = self._collection().document(str(production_id)).collection("members").document(user_id)  # type: ignore[union-attr]
        snapshot = member.get()
        if not snapshot.exists or snapshot.to_dict().get("membership_status") != MembershipStatus.PENDING:
            raise ProductionNotFoundError()
        member.update({"membership_status": str(decision)})
        data = snapshot.to_dict() | {"membership_status": str(decision)}
        return ProductionMember(production_id=production_id, **data)

    def update(self, production_id: UUID, payload: ProductionUpdate, user_id: str) -> Production:
        caller = self._member(production_id, user_id)
        if caller.to_dict()["role"] != ProductionRole.PRODUCER:
            raise ProductionPermissionError()
        reference = self._collection().document(str(production_id))  # type: ignore[union-attr]
        snapshot = reference.get()
        if not snapshot.exists:
            raise ProductionNotFoundError()
        updated_at = datetime.now(timezone.utc)
        reference.update({"name": payload.name.strip(), "updated_at": updated_at})
        return self._from_data(str(production_id), snapshot.to_dict() | {"name": payload.name.strip(), "updated_at": updated_at}, ProductionRole.PRODUCER)


def create_production_repository(db: Session | None = None) -> ProductionDataRepository:
    if settings.is_firestore:
        return FirestoreProductionRepository()
    if db is None:
        raise RuntimeError("Se requiere una sesión SQLAlchemy para SQLite.")
    return ProductionRepository(db)
