"""Tests for Firebase authentication without external Firebase calls."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.core import security
from app.core.config import settings


def test_local_mode_returns_a_stable_development_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "auth_required", False)
    assert security.get_current_user().uid == "local-supervisor"


def test_missing_bearer_token_is_rejected_when_auth_is_required(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "auth_required", True)
    monkeypatch.setattr(settings, "google_cloud_project", "frameflow-test")
    with pytest.raises(HTTPException) as error:
        security.get_current_user(None)
    assert error.value.status_code == 401


def test_verified_firebase_token_returns_only_safe_identity_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "auth_required", True)
    monkeypatch.setattr(settings, "google_cloud_project", "frameflow-test")
    monkeypatch.setattr(security, "_initialise_firebase", lambda: None)

    from firebase_admin import auth

    monkeypatch.setattr(
        auth,
        "verify_id_token",
        lambda token: {"uid": "user-123", "email": "supervisor@example.com", "name": "Supervisor", "picture": "https://example.com/avatar.jpg"},
    )

    user = security.get_current_user("Bearer valid-token")
    assert (user.uid, user.email, user.name) == ("user-123", "supervisor@example.com", "Supervisor")
    assert user.photo_url == "https://example.com/avatar.jpg"


def test_invalid_firebase_token_is_rejected_without_leaking_provider_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "auth_required", True)
    monkeypatch.setattr(settings, "google_cloud_project", "frameflow-test")
    monkeypatch.setattr(security, "_initialise_firebase", lambda: None)

    from firebase_admin import auth

    monkeypatch.setattr(auth, "verify_id_token", lambda token: (_ for _ in ()).throw(ValueError("secret provider detail")))
    with pytest.raises(HTTPException) as error:
        security.get_current_user("Bearer invalid-token")
    assert error.value.status_code == 401
    assert error.value.detail == "Invalid or expired session."
