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
        TicketWorkUpdate(
            status=ArtistWorkStatus.READY_FOR_QC,
            artist_note="Roto limpio terminado.",
            delivery_link="https://example.com/revision-01",
        ),
    )
    completed = repository.quality_review(
        created.id,
        TicketQualityReview(decision=QualityDecision.APPROVE, supervisor_feedback="QC aprobado."),
    )

    assert in_progress.status is TicketStatus.IN_PROGRESS
    assert ready.status is TicketStatus.READY_FOR_QC
    assert ready.artist_note == "Roto limpio terminado."
    assert ready.delivery_link == "https://example.com/revision-01"
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


def test_evidence_can_only_attach_while_artist_is_working(db_session) -> None:
    repository = TicketRepository(db_session)
    created = repository.create(_ticket())
    repository.review(created.id, TicketReview(decision=ReviewDecision.APPROVE))
    repository.update_work(created.id, TicketWorkUpdate(status=ArtistWorkStatus.IN_PROGRESS))

    with_evidence = repository.attach_evidence(
        created.id,
        "gs://test-bucket/deliveries/evidence/proof.png",
        "proof.png",
        "image/png",
    )

    assert with_evidence.evidence_name == "proof.png"
    assert with_evidence.evidence_content_type == "image/png"

    without_evidence = repository.clear_evidence(created.id)

    assert without_evidence.evidence_gcs_uri is None
    assert without_evidence.evidence_name is None


def test_artist_can_clear_delivery_link_while_working(db_session) -> None:
    repository = TicketRepository(db_session)
    created = repository.create(_ticket())
    repository.review(created.id, TicketReview(decision=ReviewDecision.APPROVE))
    repository.update_work(created.id, TicketWorkUpdate(status=ArtistWorkStatus.IN_PROGRESS))
    with_link = repository.update_work(
        created.id,
        TicketWorkUpdate(status=ArtistWorkStatus.IN_PROGRESS, delivery_link="https://example.com/delivery"),
    )

    without_link = repository.clear_delivery_link(created.id)

    assert with_link.delivery_link == "https://example.com/delivery"
    assert without_link.delivery_link is None
