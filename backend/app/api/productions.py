"""Authenticated endpoints for the production/team foundation."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import CurrentUser, get_current_user
from app.database import get_db
from app.models.production import InvitationResponse, MembershipStatus, Production, ProductionCreate, ProductionMember, ProductionMemberCreate, ProductionRole, ProductionUpdate
from app.services.production_repository import ProductionDataRepository, ProductionNotFoundError, ProductionPermissionError, create_production_repository
from app.services.production_repository import ProductionMemberRemovalError
from app.services.ticket_repository import TicketDataRepository, create_ticket_repository
from app.models.notification import NotificationType
from app.services.notification_repository import NotificationDataRepository, create_notification_repository
from app.models.user_profile import UserProfile
from app.services.user_profile_repository import UserProfileDataRepository, create_user_profile_repository
from app.api.profiles import resolve_profile

router = APIRouter(prefix="/productions", tags=["Productions"])


def _repo(db: Session | None = Depends(get_db)) -> ProductionDataRepository:
    return create_production_repository(db)


def _ticket_repo(db: Session | None = Depends(get_db)) -> TicketDataRepository:
    return create_ticket_repository(db)


def _notification_repo(db: Session | None = Depends(get_db)) -> NotificationDataRepository:
    return create_notification_repository(db)


def _profile_repo(db: Session | None = Depends(get_db)) -> UserProfileDataRepository:
    return create_user_profile_repository(db)


def _hydrate_member(member: ProductionMember, profile: UserProfile | None) -> ProductionMember:
    if profile is None:
        return member
    return member.model_copy(update={
        "display_name": profile.display_name,
        "username": profile.username,
        "photo_url": profile.photo_url,
        "has_custom_avatar": profile.has_custom_avatar,
        "profile_updated_at": profile.updated_at,
    })


@router.post("/bootstrap", response_model=Production)
async def bootstrap_production(repo: ProductionDataRepository = Depends(_repo), user: CurrentUser = Depends(get_current_user)) -> Production:
    return repo.bootstrap_personal(user.uid, user.name, user.email)


@router.get("", response_model=list[Production])
async def list_productions(repo: ProductionDataRepository = Depends(_repo), user: CurrentUser = Depends(get_current_user)) -> list[Production]:
    return repo.list_for_user(user.uid)


@router.post("", response_model=Production, status_code=status.HTTP_201_CREATED)
async def create_production(payload: ProductionCreate, repo: ProductionDataRepository = Depends(_repo), user: CurrentUser = Depends(get_current_user)) -> Production:
    return repo.create(payload, user.uid)


@router.get("/invitations", response_model=list[ProductionMember])
async def list_invitations(repo: ProductionDataRepository = Depends(_repo), profiles: UserProfileDataRepository = Depends(_profile_repo), user: CurrentUser = Depends(get_current_user)) -> list[ProductionMember]:
    profiles.ensure(user)
    return [
        invitation.model_copy(
            update={
                "invited_by": resolve_profile(invitation.invited_by_uid, profiles)
                if invitation.invited_by_uid
                else None
            }
        )
        for invitation in repo.list_invitations(user.uid)
    ]


@router.post("/{production_id}/invitation-response", response_model=ProductionMember)
async def respond_to_invitation(production_id: UUID, payload: InvitationResponse, repo: ProductionDataRepository = Depends(_repo), profiles: UserProfileDataRepository = Depends(_profile_repo), user: CurrentUser = Depends(get_current_user)) -> ProductionMember:
    if payload.decision not in {MembershipStatus.ACCEPTED, MembershipStatus.DECLINED}:
        raise HTTPException(status_code=422, detail="La invitación debe aceptarse o rechazarse.")
    try:
        return _hydrate_member(repo.respond_to_invitation(production_id, user.uid, payload.decision), profiles.ensure(user))
    except ProductionNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Invitación no encontrada.") from exc


@router.patch("/{production_id}", response_model=Production)
async def update_production(production_id: UUID, payload: ProductionUpdate, repo: ProductionDataRepository = Depends(_repo), user: CurrentUser = Depends(get_current_user)) -> Production:
    try:
        return repo.update(production_id, payload, user.uid)
    except ProductionNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Producción no encontrada.") from exc
    except ProductionPermissionError as exc:
        raise HTTPException(status_code=403, detail="Solo el productor puede renombrar la producción.") from exc


@router.get("/{production_id}/members", response_model=list[ProductionMember])
async def list_members(production_id: UUID, repo: ProductionDataRepository = Depends(_repo), profiles: UserProfileDataRepository = Depends(_profile_repo), user: CurrentUser = Depends(get_current_user)) -> list[ProductionMember]:
    try:
        return [
            _hydrate_member(member, resolve_profile(member.uid, profiles))
            for member in repo.list_members(production_id, user.uid)
        ]
    except ProductionNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Producción no encontrada.") from exc


@router.post("/{production_id}/members", response_model=ProductionMember, status_code=status.HTTP_201_CREATED)
async def add_member(production_id: UUID, payload: ProductionMemberCreate, repo: ProductionDataRepository = Depends(_repo), profiles: UserProfileDataRepository = Depends(_profile_repo), notifications: NotificationDataRepository = Depends(_notification_repo), user: CurrentUser = Depends(get_current_user)) -> ProductionMember:
    try:
        if payload.role is ProductionRole.PRODUCER:
            raise HTTPException(status_code=422, detail="La producción solo puede tener un productor propietario.")
        if payload.uid == user.uid:
            raise HTTPException(status_code=409, detail="Ya eres productor de esta producción.")
        target_profile = resolve_profile(payload.uid, profiles)
        if target_profile is None:
            raise HTTPException(status_code=404, detail="No encontramos un usuario de FrameFlow con esa identidad.")
        inviter_profile = profiles.ensure(user)
        existing = next((item for item in repo.list_members(production_id, user.uid) if item.uid == payload.uid), None)
        if existing and existing.role.value == "producer":
            raise HTTPException(status_code=403, detail="No puedes modificar al productor de la producción.")
        member = _hydrate_member(repo.add_member(production_id, payload, user.uid), target_profile)
        should_notify = existing is None or existing.membership_status is MembershipStatus.DECLINED
        if member.membership_status is MembershipStatus.PENDING and should_notify:
            notifications.create(member.uid, NotificationType.INVITATION, "Nueva invitación", f"{inviter_profile.display_name} (@{inviter_profile.username}) te invitó a una producción. Revisa y responde la invitación.", production_id=production_id)
        return member
    except ProductionNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Producción no encontrada.") from exc
    except ProductionPermissionError as exc:
        raise HTTPException(status_code=403, detail="Solo el productor puede gestionar el equipo.") from exc


@router.delete("/{production_id}/members/{member_uid}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(production_id: UUID, member_uid: str, repo: ProductionDataRepository = Depends(_repo), tickets: TicketDataRepository = Depends(_ticket_repo), user: CurrentUser = Depends(get_current_user)) -> None:
    """Remove a member and return their active tickets to pending supervisor review."""
    try:
        repo.remove_member(production_id, member_uid, user.uid)
        tickets.unassign_member_tasks(production_id, member_uid)
    except ProductionNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Miembro o producción no encontrados.") from exc
    except (ProductionPermissionError, ProductionMemberRemovalError) as exc:
        raise HTTPException(status_code=403, detail="No puedes retirar a este miembro.") from exc
