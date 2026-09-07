"""Tests for the local production and membership foundation."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.production import MembershipStatus, ProductionCreate, ProductionMemberCreate, ProductionRole, ProductionUpdate
from app.models.ticket import Department
from app.services.production_repository import ProductionPermissionError, ProductionRepository
from app.services.ticket_repository import TicketRepository
from app.models.ticket import Priority, ReviewDecision, TicketCreate, TicketReview, TicketStatus


@pytest.fixture()
def repository() -> ProductionRepository:
    engine = create_engine("sqlite:///:memory:")
    import app.models.production_record  # noqa: F401

    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield ProductionRepository(session)
    session.close()
    engine.dispose()


def test_bootstrap_creates_one_personal_production(repository: ProductionRepository) -> None:
    first = repository.bootstrap_personal("supervisor", "Ana Supervisor", "ana@example.com")
    second = repository.bootstrap_personal("supervisor", "Ana Supervisor", "ana@example.com")

    assert first.id == second.id
    assert first.current_user_role is ProductionRole.PRODUCER
    assert len(repository.list_for_user("supervisor")) == 1


def test_producer_invites_artist_who_must_accept_before_seeing_production(repository: ProductionRepository) -> None:
    production = repository.create(ProductionCreate(name="Corto Nebula"), "producer")
    artist = repository.add_member(
        production.id,
        ProductionMemberCreate(uid="artist", role=ProductionRole.ARTIST, department=Department.VFX, display_name="Kai"),
        "producer",
    )

    assert artist.role is ProductionRole.ARTIST
    assert artist.department is Department.VFX
    assert artist.membership_status is MembershipStatus.PENDING
    assert repository.list_for_user("artist") == []
    invitation = repository.list_invitations("artist")[0]
    repository.respond_to_invitation(production.id, "artist", MembershipStatus.ACCEPTED)
    assert invitation.production_id == production.id
    assert invitation.invited_by_uid == "producer"
    assert repository.list_for_user("artist")[0].id == production.id


def test_only_producer_can_manage_members(repository: ProductionRepository) -> None:
    production = repository.create(ProductionCreate(name="Corto Nebula"), "producer")
    repository.add_member(production.id, ProductionMemberCreate(uid="supervisor", role=ProductionRole.SUPERVISOR), "producer")

    with pytest.raises(ProductionPermissionError):
        repository.add_member(production.id, ProductionMemberCreate(uid="artist", role=ProductionRole.ARTIST), "supervisor")


def test_tickets_can_be_scoped_to_a_production(repository: ProductionRepository) -> None:
    production = repository.create(ProductionCreate(name="Corto Nebula"), "producer")
    other_production = repository.create(ProductionCreate(name="Corto Aurora"), "producer")
    ticket_repo = TicketRepository(repository._db)
    ticket = ticket_repo.create(
        TicketCreate(shot_id="TEAM-001", director_note="Eliminar el boom.", department=Department.VFX, priority=Priority.HIGH),
        owner_id="producer",
        production_id=production.id,
    )
    ticket_repo.create(
        TicketCreate(shot_id="TEAM-002", director_note="Mezclar diálogo.", department=Department.SOUND, priority=Priority.MEDIUM),
        owner_id="producer",
        production_id=other_production.id,
    )
    ticket_repo.create(
        TicketCreate(shot_id="LEGACY-001", director_note="Ticket anterior.", department=Department.VFX, priority=Priority.LOW),
        owner_id="producer",
    )

    assert ticket.production_id == production.id
    assert [result.id for result in ticket_repo.list(production_id=production.id)] == [ticket.id]


def test_only_producer_can_rename_production(repository: ProductionRepository) -> None:
    production = repository.create(ProductionCreate(name="Corto Nebula"), "producer")
    renamed = repository.update(production.id, ProductionUpdate(name="Corto Aurora"), "producer")

    assert renamed.name == "Corto Aurora"


def test_removing_artist_returns_active_ticket_to_pending_review(repository: ProductionRepository) -> None:
    production = repository.create(ProductionCreate(name="Corto Nebula"), "producer")
    repository.add_member(production.id, ProductionMemberCreate(uid="artist", role=ProductionRole.ARTIST, department=Department.VFX), "producer")
    repository.respond_to_invitation(production.id, "artist", MembershipStatus.ACCEPTED)
    tickets = TicketRepository(repository._db)
    created = tickets.create(TicketCreate(shot_id="TEAM-002", director_note="Eliminar el boom.", department=Department.VFX, priority=Priority.HIGH), production_id=production.id)
    tickets.review(created.id, TicketReview(decision=ReviewDecision.APPROVE, assigned_to_uid="artist", assigned_to_name="Kai"), production_id=production.id)

    assert tickets.unassign_member_tasks(production.id, "artist") == 1
    repository.remove_member(production.id, "artist", "producer")

    assert tickets.list(production_id=production.id)[0].status is TicketStatus.PENDING_REVIEW
    assert tickets.list(production_id=production.id)[0].assigned_to_uid is None
    assert all(member.uid != "artist" for member in repository.list_members(production.id, "producer"))
