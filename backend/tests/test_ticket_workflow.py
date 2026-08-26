"""Workflow v1 transition tests for supervisor and artist actions."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.ticket import (
    ArtistWorkStatus,
    Department,
    Priority,
    QualityDecision,
    ReviewDecision,
    TicketCreate,
    TicketQualityReview,
    TicketReview,
    TicketStatus,
    TicketWorkUpdate,
)
from app.services.ticket_repository import TicketRepository, TicketTransitionError


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    import app.models.ticket_record  # noqa: F401

    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine, autocommit=False, autoflush=False)()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def _ticket() -> TicketCreate:
    return TicketCreate(
        shot_id="WORKFLOW-001",
        director_note="Eliminar el micrófono del plano.",
        department=Department.VFX,
        priority=Priority.HIGH,
    )


def test_approved_ticket_moves_through_artist_and_qc_lifecycle(db_session) -> None:
    repository = TicketRepository(db_session)
    created = repository.create(_ticket())
    assigned = repository.review(created.id, TicketReview(decision=ReviewDecision.APPROVE))
    assert assigned.status is TicketStatus.ASSIGNED

    in_progress = repository.update_work(
        created.id, TicketWorkUpdate(status=ArtistWorkStatus.IN_PROGRESS)
    )
    ready = repository.update_work(
        created.id,
        TicketWorkUpdate(status=ArtistWorkStatus.READY_FOR_QC, artist_note="Roto limpio terminado."),
    )
    completed = repository.quality_review(
        created.id,
        TicketQualityReview(decision=QualityDecision.APPROVE, supervisor_feedback="QC aprobado."),
    )

    assert in_progress.status is TicketStatus.IN_PROGRESS
    assert ready.status is TicketStatus.READY_FOR_QC
    assert ready.artist_note == "Roto limpio terminado."
    assert completed.status is TicketStatus.COMPLETED
    assert completed.supervisor_feedback == "QC aprobado."


def test_qc_return_sends_ticket_back_to_artist(db_session) -> None:
    repository = TicketRepository(db_session)
    created = repository.create(_ticket())
    repository.review(created.id, TicketReview(decision=ReviewDecision.APPROVE))
    repository.update_work(created.id, TicketWorkUpdate(status=ArtistWorkStatus.IN_PROGRESS))
    repository.update_work(created.id, TicketWorkUpdate(status=ArtistWorkStatus.READY_FOR_QC))

    returned = repository.quality_review(
        created.id,
        TicketQualityReview(
            decision=QualityDecision.RETURN_FOR_REWORK,
            supervisor_feedback="Quedan bordes del micrófono en el cabello.",
        ),
    )

    assert returned.status is TicketStatus.IN_PROGRESS
    assert returned.supervisor_feedback is not None


def test_cannot_send_assigned_ticket_to_qc_without_starting_work(db_session) -> None:
    repository = TicketRepository(db_session)
    created = repository.create(_ticket())
    repository.review(created.id, TicketReview(decision=ReviewDecision.APPROVE))

    try:
        repository.update_work(created.id, TicketWorkUpdate(status=ArtistWorkStatus.READY_FOR_QC))
    except TicketTransitionError:
        pass
    else:  # pragma: no cover - documents the expected transition guard
        raise AssertionError("Expected TicketTransitionError")
