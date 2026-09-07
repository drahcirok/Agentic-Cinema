"""Authenticated profile, avatar and member-directory endpoints."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import CurrentUser, get_current_user
from app.database import get_db
from app.models.user_profile import UserProfile, UserProfileUpdate
from app.models.production import MembershipStatus, ProductionRole
from app.services.production_repository import (
    ProductionDataRepository,
    ProductionNotFoundError,
    create_production_repository,
)
from app.services.user_profile_repository import (
    InvalidUsernameError,
    ProfileNotFoundError,
    UserProfileDataRepository,
    UsernameUnavailableError,
    create_user_profile_repository,
    is_valid_firebase_uid,
)
from app.services.video_storage import (
    ALLOWED_AVATAR_MIME_TYPES,
    MAX_AVATAR_SIZE_BYTES,
    StorageConfigurationError,
    video_storage,
)

router = APIRouter(prefix="/profiles", tags=["Profiles"])


def _repo(db: Session | None = Depends(get_db)) -> UserProfileDataRepository:
    return create_user_profile_repository(db)


def _production_repo(db: Session | None = Depends(get_db)) -> ProductionDataRepository:
    return create_production_repository(db)


def _firebase_profile(uid: str, repo: UserProfileDataRepository) -> UserProfile | None:
    """Materialise an exact Firebase UID that has not opened the new UI yet."""
    if not settings.auth_required:
        return None
    try:
        from app.core.security import _initialise_firebase
        from firebase_admin import auth

        _initialise_firebase()
        record = auth.get_user(uid)
        return repo.ensure(
            CurrentUser(
                uid=record.uid,
                email=record.email,
                name=record.display_name,
                photo_url=record.photo_url,
            )
        )
    except Exception:
        return None


def resolve_profile(uid: str, repo: UserProfileDataRepository) -> UserProfile | None:
    if not is_valid_firebase_uid(uid):
        return None
    return repo.get(uid) or _firebase_profile(uid, repo)


def get_current_profile(
    repo: UserProfileDataRepository = Depends(_repo),
    user: CurrentUser = Depends(get_current_user),
) -> UserProfile:
    """Shared dependency so audit events use the editable FrameFlow name."""
    return repo.ensure(user)


@router.get("/me", response_model=UserProfile)
async def get_my_profile(
    repo: UserProfileDataRepository = Depends(_repo),
    user: CurrentUser = Depends(get_current_user),
) -> UserProfile:
    return repo.ensure(user)


@router.patch("/me", response_model=UserProfile)
async def update_my_profile(
    payload: UserProfileUpdate,
    repo: UserProfileDataRepository = Depends(_repo),
    user: CurrentUser = Depends(get_current_user),
) -> UserProfile:
    repo.ensure(user)
    try:
        return repo.update(user.uid, payload)
    except InvalidUsernameError as exc:
        raise HTTPException(
            status_code=422,
            detail="El usuario debe tener entre 3 y 30 caracteres y usar solo letras, números, punto, guion o guion bajo.",
        ) from exc
    except UsernameUnavailableError as exc:
        raise HTTPException(status_code=409, detail="Ese nombre de usuario ya está ocupado.") from exc


@router.get("/search", response_model=list[UserProfile])
async def search_profiles(
    q: str = Query(min_length=2, max_length=128),
    production_id: str = Query(min_length=36, max_length=36),
    repo: UserProfileDataRepository = Depends(_repo),
    productions: ProductionDataRepository = Depends(_production_repo),
    user: CurrentUser = Depends(get_current_user),
) -> list[UserProfile]:
    repo.ensure(user)
    try:
        parsed_production_id = UUID(production_id)
        caller = next(
            member
            for member in productions.list_members(parsed_production_id, user.uid)
            if member.uid == user.uid
        )
        if caller.role is not ProductionRole.PRODUCER or caller.membership_status is not MembershipStatus.ACCEPTED:
            raise HTTPException(status_code=403, detail="Solo el productor puede buscar e invitar integrantes.")
    except (ValueError, StopIteration, ProductionNotFoundError) as exc:
        raise HTTPException(status_code=404, detail="Producción no encontrada o sin acceso.") from exc
    results = repo.search(q, exclude_uid=user.uid)
    if not results and is_valid_firebase_uid(q):
        exact = resolve_profile(q.strip(), repo)
        if exact and exact.uid != user.uid:
            return [exact]
    return results


@router.post("/me/avatar", response_model=UserProfile)
async def upload_my_avatar(
    avatar: UploadFile = File(...),
    repo: UserProfileDataRepository = Depends(_repo),
    user: CurrentUser = Depends(get_current_user),
) -> UserProfile:
    repo.ensure(user)
    mime_type = (avatar.content_type or "").lower()
    if mime_type not in ALLOWED_AVATAR_MIME_TYPES:
        raise HTTPException(status_code=415, detail="La foto debe ser JPG, PNG o WEBP.")
    content = await avatar.read(MAX_AVATAR_SIZE_BYTES + 1)
    if len(content) > MAX_AVATAR_SIZE_BYTES:
        raise HTTPException(status_code=413, detail="La foto no puede superar 2 MB.")
    # The MIME type is authoritative. A renamed file must not be stored and
    # later served with a contradictory extension/content type.
    extension = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}[mime_type]
    try:
        gs_uri = video_storage.upload_avatar(content, mime_type, extension)
        profile, previous = repo.set_avatar(user.uid, gs_uri)
        if previous:
            video_storage.delete_object(previous)
        return profile
    except (StorageConfigurationError, ValueError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.delete("/me/avatar", response_model=UserProfile)
async def delete_my_avatar(
    repo: UserProfileDataRepository = Depends(_repo),
    user: CurrentUser = Depends(get_current_user),
) -> UserProfile:
    repo.ensure(user)
    profile, previous = repo.clear_avatar(user.uid)
    if previous:
        video_storage.delete_object(previous)
    return profile


@router.get("/{uid}/avatar")
async def download_profile_avatar(
    uid: str,
    repo: UserProfileDataRepository = Depends(_repo),
    user: CurrentUser = Depends(get_current_user),
) -> Response:
    repo.ensure(user)
    gs_uri = repo.avatar_uri(uid)
    if not gs_uri:
        raise HTTPException(status_code=404, detail="Este perfil no tiene una foto personalizada.")
    try:
        content = video_storage.download_avatar(gs_uri)
    except (StorageConfigurationError, ValueError):
        raise HTTPException(status_code=404, detail="Foto de perfil no disponible.") from None
    suffix = Path(gs_uri).suffix.lower()
    mime_type = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}.get(suffix, "image/jpeg")
    return Response(content=content, media_type=mime_type, headers={"Cache-Control": "private, max-age=300"})
