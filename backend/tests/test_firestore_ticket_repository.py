"""Unit tests for Firestore ticket persistence without Google Cloud I/O."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest

from app.models.ticket import Department, Priority, ReviewDecision, TicketCreate, TicketReview
from app.services.ticket_repository import FirestoreTicketRepository, TicketNotFoundError


class FakeSnapshot:
    def __init__(self, document_id: str, data: dict[str, object] | None) -> None:
        self.id = document_id
        self._data = data
        self.exists = data is not None

    def to_dict(self) -> dict[str, object]:
        assert self._data is not None
        return dict(self._data)


class FakeDocumentReference:
    def __init__(self, collection: "FakeCollection", document_id: str) -> None:
        self._collection = collection
        self._document_id = document_id

    def set(self, data: dict[str, object]) -> None:
        self._collection.documents[self._document_id] = dict(data)

    def get(self) -> FakeSnapshot:
        return FakeSnapshot(self._document_id, self._collection.documents.get(self._document_id))

    def update(self, changes: dict[str, object]) -> None:
        self._collection.documents[self._document_id].update(changes)


class FakeCollection:
    def __init__(self) -> None:
        self.documents: dict[str, dict[str, object]] = {}
        self.order_by_args: tuple[str, object] | None = None

    def document(self, document_id: str) -> FakeDocumentReference:
        return FakeDocumentReference(self, document_id)

    def order_by(self, field: str, direction: object) -> "FakeCollection":
        self.order_by_args = (field, direction)
        return self

    def where(self, field: str, operator: str, value: object) -> "FakeCollection":
        assert operator == "=="
        filtered = FakeCollection()
        filtered.documents = {
            document_id: data
            for document_id, data in self.documents.items()
            if data.get(field) == value
        }
        return filtered

    def stream(self) -> list[FakeSnapshot]:
        return [
            FakeSnapshot(document_id, data)
            for document_id, data in sorted(
                self.documents.items(),
                key=lambda item: item[1]["created_at"],
                reverse=True,
            )
        ]


class FakeFirestoreClient:
    def __init__(self) -> None:
        self.collections: dict[str, FakeCollection] = {}

    def collection(self, name: str) -> FakeCollection:
        return self.collections.setdefault(name, FakeCollection())


def _payload(shot_id: str = "SC01-SH001") -> TicketCreate:
    return TicketCreate(
        shot_id=shot_id,
        director_note="Eliminar el micrófono del encuadre.",
        department=Department.VFX,
        priority=Priority.HIGH,
        ai_rationale="El micrófono debe eliminarse mediante composición VFX.",
    )


@pytest.fixture
def repository() -> FirestoreTicketRepository:
    return FirestoreTicketRepository(client=FakeFirestoreClient(), collection_name="tickets_test")


def test_create_persists_and_returns_ticket(repository: FirestoreTicketRepository) -> None:
    created = repository.create(_payload())

    assert isinstance(created.id, UUID)
    assert created.shot_id == "SC01-SH001"
    assert created.status.value == "pending_review"
    assert created.ai_rationale is not None


def test_edit_keeps_pending_and_persists_changes(repository: FirestoreTicketRepository) -> None:
    created = repository.create(_payload())

    updated = repository.review(
        created.id,
        TicketReview(
            decision=ReviewDecision.EDIT,
            department=Department.SOUND,
            priority=Priority.CRITICAL,
            supervisor_note="Confirmar mezcla final antes de aprobar.",
        ),
    )

    assert updated.department.value == "sound"
    assert updated.priority.value == "critical"
    assert updated.status.value == "pending_review"
    assert updated.supervisor_note == "Confirmar mezcla final antes de aprobar."


def test_approve_persists_and_list_returns_newest_first(repository: FirestoreTicketRepository) -> None:
    older_id = str(uuid4())
    newer_id = str(uuid4())
    collection = repository._get_collection()
    collection.document(older_id).set({
        "owner_id": "local-supervisor",
        "shot_id": "SC01-SH001", "director_note": "Nota antigua", "department": "vfx",
        "priority": "medium", "status": "pending_review", "ai_rationale": None,
        "supervisor_note": None, "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
    })
    collection.document(newer_id).set({
        "owner_id": "local-supervisor",
        "shot_id": "SC01-SH002", "director_note": "Nota nueva", "department": "color",
        "priority": "high", "status": "pending_review", "ai_rationale": None,
        "supervisor_note": None, "created_at": datetime(2026, 1, 2, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 1, 2, tzinfo=timezone.utc),
    })

    approved = repository.review(UUID(newer_id), TicketReview(decision=ReviewDecision.APPROVE))
    tickets = repository.list()

    assert approved.status.value == "assigned"
    assert [ticket.id for ticket in tickets] == [UUID(newer_id), UUID(older_id)]


def test_review_unknown_ticket_raises_not_found(repository: FirestoreTicketRepository) -> None:
    with pytest.raises(TicketNotFoundError):
        repository.review(uuid4(), TicketReview(decision=ReviewDecision.REJECT))


def test_tickets_are_scoped_to_their_owner(repository: FirestoreTicketRepository) -> None:
    alice_ticket = repository.create(_payload("ALICE-001"), owner_id="alice")
    repository.create(_payload("BOB-001"), owner_id="bob")

    assert [ticket.id for ticket in repository.list(owner_id="alice")] == [alice_ticket.id]
    with pytest.raises(TicketNotFoundError):
        repository.review(alice_ticket.id, TicketReview(decision=ReviewDecision.APPROVE), owner_id="bob")


def test_tickets_are_strictly_scoped_to_the_active_production(repository: FirestoreTicketRepository) -> None:
    production_id = uuid4()
    other_production_id = uuid4()
    visible = repository.create(_payload("AURORA-001"), owner_id="producer", production_id=production_id)
    repository.create(_payload("OTHER-001"), owner_id="producer", production_id=other_production_id)
    repository.create(_payload("LEGACY-001"), owner_id="producer")

    assert [ticket.id for ticket in repository.list(owner_id="producer", production_id=production_id)] == [visible.id]
