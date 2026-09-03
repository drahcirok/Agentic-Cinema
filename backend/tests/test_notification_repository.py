"""Tests for the private in-app notification inbox."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.notification import NotificationType
from app.models.notification_record import NotificationRecord  # noqa: F401
from app.services.notification_repository import NotificationNotFoundError, NotificationRepository


def test_notifications_are_private_and_can_be_marked_read() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    repository = NotificationRepository(session)

    created = repository.create(
        "artist-a",
        NotificationType.TASK_ASSIGNED,
        "Nueva tarea asignada",
        "SC01-SH001 fue asignada.",
    )

    assert [item.id for item in repository.list_for_user("artist-a")] == [created.id]
    assert repository.list_for_user("artist-b") == []
    assert repository.mark_read(created.id, "artist-a").read_at is not None

    try:
        repository.mark_read(created.id, "artist-b")
    except NotificationNotFoundError:
        pass
    else:  # pragma: no cover
        raise AssertionError("A user must not read another user's notification")

    session.close()
    engine.dispose()
