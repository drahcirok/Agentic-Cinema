"""Tests for persisted ticket activity timelines."""

from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.ticket_activity_record import TicketActivityRecord  # noqa: F401
from app.services.ticket_activity_repository import TicketActivityRepository


def test_activity_is_scoped_to_the_ticket_and_ordered_newest_first() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    repository = TicketActivityRepository(session)
    ticket_id, other_ticket_id = uuid4(), uuid4()

    repository.record(ticket_id, None, "supervisor", "Sofía", "Ticket creado")
    repository.record(ticket_id, None, "artist", "Fabián", "Trabajo iniciado")
    repository.record(other_ticket_id, None, "artist", "Otro", "No aparece")

    activity = repository.list_for_ticket(ticket_id, None)
    assert [item.action for item in activity] == ["Trabajo iniciado", "Ticket creado"]
    assert {item.actor_name for item in activity} == {"Sofía", "Fabián"}

    session.close()
    engine.dispose()
