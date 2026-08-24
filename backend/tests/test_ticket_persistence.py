"""Persistence tests for TicketRepository.

These tests verify that tickets survive across database sessions — which is the
key guarantee that SQLite provides over the previous in-memory TicketStore.

Each test creates its own isolated in-memory SQLite database so the test suite
is hermetic and leaves no files on disk.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.ticket import Department, Priority, ReviewDecision, TicketCreate, TicketReview, TicketStatus
from app.services.ticket_repository import TicketNotFoundError, TicketRepository


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def engine():
    """Fresh in-memory SQLite engine per test."""
    _engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    # Register ORM models so ticket_record table is created.
    import app.models.ticket_record  # noqa: F401

    Base.metadata.create_all(bind=_engine)
    yield _engine
    Base.metadata.drop_all(bind=_engine)
    _engine.dispose()


@pytest.fixture()
def make_session(engine):
    """Factory that returns a *new* session bound to the shared engine.

    Calling it twice simulates two separate requests / server restarts that
    share the same underlying file.
    """
    factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    def _make():
        return factory()

    return _make


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _sample_payload(**overrides) -> TicketCreate:
    defaults = dict(
        shot_id="SC01-SH001",
        director_note="Remove the mic from the frame.",
        department=Department.VFX,
        priority=Priority.HIGH,
        ai_rationale="Microphone visible in top-left corner.",
    )
    defaults.update(overrides)
    return TicketCreate(**defaults)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestTicketPersistenceAcrossSessions:
    """Core persistence guarantee: data written in one session is readable in another."""

    def test_ticket_exists_in_second_session(self, make_session):
        """A ticket created in session A is visible in an independent session B."""
        # Session A: create
        session_a = make_session()
        repo_a = TicketRepository(session_a)
        created = repo_a.create(_sample_payload())
        session_a.close()

        # Session B: read — no reference to session_a
        session_b = make_session()
        repo_b = TicketRepository(session_b)
        tickets = repo_b.list()
        session_b.close()

        assert len(tickets) == 1
        assert tickets[0].id == created.id

    def test_all_fields_survive_round_trip(self, make_session):
        """Every field stored in session A is faithfully returned in session B."""
        payload = _sample_payload(
            shot_id="SC05-SH022",
            director_note="Colour-grade the sunset to orange.",
            department=Department.COLOR,
            priority=Priority.CRITICAL,
            ai_rationale="Sky requires warm grade.",
        )
        session_a = make_session()
        created = TicketRepository(session_a).create(payload)
        session_a.close()

        session_b = make_session()
        tickets = TicketRepository(session_b).list()
        session_b.close()

        t = tickets[0]
        assert t.id == created.id
        assert t.shot_id == "SC05-SH022"
        assert t.director_note == "Colour-grade the sunset to orange."
        assert t.department == Department.COLOR
        assert t.priority == Priority.CRITICAL
        assert t.ai_rationale == "Sky requires warm grade."
        assert t.status == TicketStatus.PENDING_REVIEW
        assert t.supervisor_note is None

    def test_review_persists_across_sessions(self, make_session):
        """A review decision written in session A is visible in session B."""
        session_a = make_session()
        created = TicketRepository(session_a).create(_sample_payload())
        session_a.close()

        # Review in session B
        review = TicketReview(
            decision=ReviewDecision.APPROVE,
            supervisor_note="Looks good, approved.",
        )
        session_b = make_session()
        TicketRepository(session_b).review(created.id, review)
        session_b.close()

        # Verify in session C
        session_c = make_session()
        tickets = TicketRepository(session_c).list()
        session_c.close()

        assert tickets[0].status == TicketStatus.APPROVED
        assert tickets[0].supervisor_note == "Looks good, approved."

    def test_rejection_persists_across_sessions(self, make_session):
        """A rejected ticket keeps its status in a new session."""
        session_a = make_session()
        created = TicketRepository(session_a).create(_sample_payload())
        session_a.close()

        session_b = make_session()
        TicketRepository(session_b).review(
            created.id,
            TicketReview(decision=ReviewDecision.REJECT, supervisor_note="Not acceptable."),
        )
        session_b.close()

        session_c = make_session()
        tickets = TicketRepository(session_c).list()
        session_c.close()

        assert tickets[0].status == TicketStatus.REJECTED

    def test_multiple_tickets_all_persist(self, make_session):
        """Three tickets created across separate sessions are all retrievable."""
        payloads = [
            _sample_payload(shot_id=f"SC0{i}-SH00{i}", department=dept)
            for i, dept in enumerate(
                [Department.VFX, Department.COLOR, Department.SOUND], start=1
            )
        ]

        ids = []
        for p in payloads:
            s = make_session()
            ticket = TicketRepository(s).create(p)
            ids.append(ticket.id)
            s.close()

        # Fresh session sees all three
        session_final = make_session()
        all_tickets = TicketRepository(session_final).list()
        session_final.close()

        assert len(all_tickets) == 3
        persisted_ids = {t.id for t in all_tickets}
        assert persisted_ids == set(ids)

    def test_list_ordered_by_created_at_desc(self, make_session):
        """list() returns tickets newest-first."""
        import time

        ids = []
        for i in range(3):
            s = make_session()
            t = TicketRepository(s).create(_sample_payload(shot_id=f"SC0{i}-SH00{i}"))
            ids.append(t.id)
            s.close()
            time.sleep(0.01)  # ensure distinct created_at values

        s = make_session()
        tickets = TicketRepository(s).list()
        s.close()

        # Newest ticket (last created) must be first in the list
        assert tickets[0].id == ids[-1]


class TestTicketRepositoryErrors:
    def test_review_nonexistent_ticket_raises(self, make_session):
        """Reviewing an unknown ticket ID raises TicketNotFoundError."""
        from uuid import uuid4

        s = make_session()
        with pytest.raises(TicketNotFoundError):
            TicketRepository(s).review(uuid4(), TicketReview(decision=ReviewDecision.APPROVE))
        s.close()


class TestTicketStatuses:
    def test_initial_status_is_pending_review(self, make_session):
        s = make_session()
        ticket = TicketRepository(s).create(_sample_payload())
        s.close()
        assert ticket.status == TicketStatus.PENDING_REVIEW

    def test_edit_decision_keeps_pending_review(self, make_session):
        s = make_session()
        created = TicketRepository(s).create(_sample_payload())
        s.close()

        s2 = make_session()
        updated = TicketRepository(s2).review(
            created.id,
            TicketReview(decision=ReviewDecision.EDIT, priority=Priority.LOW),
        )
        s2.close()

        assert updated.status == TicketStatus.PENDING_REVIEW
        assert updated.priority == Priority.LOW
