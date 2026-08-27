"""Tests for the local production and membership foundation."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.production import ProductionCreate, ProductionMemberCreate, ProductionRole
from app.models.ticket import Department
from app.services.production_repository import ProductionPermissionError, ProductionRepository
from app.services.ticket_repository import TicketRepository
from app.models.ticket import Priority, TicketCreate


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


def test_producer_can_add_an_artist_and_artist_can_see_production(repository: ProductionRepository) -> None:
    production = repository.create(ProductionCreate(name="Corto Nebula"), "producer")
    artist = repository.add_member(
        production.id,
        ProductionMemberCreate(uid="artist", role=ProductionRole.ARTIST, department=Department.VFX, display_name="Kai"),
        "producer",
    )

    assert artist.role is ProductionRole.ARTIST
    assert artist.department is Department.VFX
    assert repository.list_for_user("artist")[0].id == production.id


def test_only_producer_can_manage_members(repository: ProductionRepository) -> None:
    production = repository.create(ProductionCreate(name="Corto Nebula"), "producer")
    repository.add_member(production.id, ProductionMemberCreate(uid="supervisor", role=ProductionRole.SUPERVISOR), "producer")

    with pytest.raises(ProductionPermissionError):
        repository.add_member(production.id, ProductionMemberCreate(uid="artist", role=ProductionRole.ARTIST), "supervisor")


def test_tickets_can_be_scoped_to_a_production(repository: ProductionRepository) -> None:
    production = repository.create(ProductionCreate(name="Corto Nebula"), "producer")
    ticket_repo = TicketRepository(repository._db)
    ticket = ticket_repo.create(
        TicketCreate(shot_id="TEAM-001", director_note="Eliminar el boom.", department=Department.VFX, priority=Priority.HIGH),
        owner_id="producer",
        production_id=production.id,
    )

    assert ticket.production_id == production.id
    assert [result.id for result in ticket_repo.list(production_id=production.id)] == [ticket.id]
