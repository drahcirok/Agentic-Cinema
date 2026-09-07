"""Tests for the local profile directory and identity rules."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.security import CurrentUser
from app.database import Base
from app.models.user_profile import UserProfileUpdate
from app.services.user_profile_repository import (
    UserProfileRepository,
    UsernameUnavailableError,
)


@pytest.fixture()
def repository() -> UserProfileRepository:
    engine = create_engine("sqlite:///:memory:")
    import app.models.user_profile_record  # noqa: F401

    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield UserProfileRepository(session)
    session.close()
    engine.dispose()


def test_profile_bootstrap_is_idempotent(repository: UserProfileRepository) -> None:
    identity = CurrentUser(uid="uid-ana", email="ana@example.com", name="Ana Ruiz", photo_url="https://example.com/ana.jpg")

    first = repository.ensure(identity)
    second = repository.ensure(identity)

    assert first.uid == second.uid
    assert first.username == "ana"
    assert second.photo_url == "https://example.com/ana.jpg"


def test_colliding_default_usernames_receive_a_suffix(repository: UserProfileRepository) -> None:
    first = repository.ensure(CurrentUser(uid="uid-first1", email="artist@example.com", name="Uno"))
    second = repository.ensure(CurrentUser(uid="uid-second2", email="artist@another.com", name="Dos"))

    assert first.username == "artist"
    assert second.username.startswith("artist-")
    assert first.username != second.username


def test_username_is_unique_and_searchable(repository: UserProfileRepository) -> None:
    ana = repository.ensure(CurrentUser(uid="uid-ana", email="ana@example.com", name="Ana Ruiz"))
    repository.ensure(CurrentUser(uid="uid-luis", email="luis@example.com", name="Luis Mora"))
    updated = repository.update(ana.uid, UserProfileUpdate(display_name="Ana VFX", username="ana.vfx"))

    assert updated.display_name == "Ana VFX"
    assert repository.search("@ana", exclude_uid="producer")[0].uid == ana.uid
    with pytest.raises(UsernameUnavailableError):
        repository.update("uid-luis", UserProfileUpdate(display_name="Luis", username="ana.vfx"))


def test_search_never_returns_the_current_user(repository: UserProfileRepository) -> None:
    repository.ensure(CurrentUser(uid="uid-ana", email="ana@example.com", name="Ana Ruiz"))

    assert repository.search("ana", exclude_uid="uid-ana") == []


def test_custom_avatar_can_be_replaced_and_cleared(repository: UserProfileRepository) -> None:
    profile = repository.ensure(CurrentUser(uid="uid-ana", email="ana@example.com", name="Ana Ruiz"))

    with_avatar, previous = repository.set_avatar(profile.uid, "gs://bucket/profiles/avatars/one.webp")
    cleared, removed = repository.clear_avatar(profile.uid)

    assert previous is None
    assert with_avatar.has_custom_avatar is True
    assert removed == "gs://bucket/profiles/avatars/one.webp"
    assert cleared.has_custom_avatar is False
