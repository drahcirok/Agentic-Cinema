"""Firebase ID-token verification for the FrameFlow API."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Header, HTTPException, status

from app.core.config import settings


@dataclass(frozen=True)
class CurrentUser:
    """Minimal identity used to scope tickets; no token is persisted."""

    uid: str
    email: str | None = None
    name: str | None = None
    photo_url: str | None = None


def _initialise_firebase() -> None:
    """Initialise Firebase Admin once with ADC, without credential files."""
    import firebase_admin
    from firebase_admin import credentials

    try:
        firebase_admin.get_app()
    except ValueError:
        firebase_admin.initialize_app(
            credentials.ApplicationDefault(),
            {"projectId": settings.google_cloud_project},
        )


def get_current_user(authorization: str | None = Header(default=None)) -> CurrentUser:
    """Return the signed-in Firebase user or a safe local-development identity."""
    if not settings.auth_required:
        return CurrentUser(uid="local-supervisor", email="local@frameflow.dev")

    settings.validate_auth()
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sign-in is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid access token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        _initialise_firebase()
        from firebase_admin import auth

        decoded = auth.verify_id_token(token)
        uid = decoded.get("uid")
        if not isinstance(uid, str) or not uid:
            raise ValueError("Firebase token has no UID")
    except Exception as exc:
        # Never return the underlying provider error or token to the caller.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    email = decoded.get("email")
    name = decoded.get("name")
    photo_url = decoded.get("picture")
    return CurrentUser(
        uid=uid,
        email=email if isinstance(email, str) else None,
        name=name if isinstance(name, str) else None,
        photo_url=photo_url if isinstance(photo_url, str) else None,
    )
