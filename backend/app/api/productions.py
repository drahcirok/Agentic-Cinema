"""Authenticated endpoints for the production/team foundation."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import CurrentUser, get_current_user
from app.database import get_db
from app.models.production import InvitationResponse, MembershipStatus, Production, ProductionCreate, ProductionMember, ProductionMemberCreate, ProductionUpdate
from app.services.production_repository import ProductionDataRepository, ProductionNotFoundError, ProductionPermissionError, create_production_repository

router = APIRouter(prefix="/productions", tags=["Productions"])


def _repo(db: Session | None = Depends(get_db)) -> ProductionDataRepository:
    return create_production_repository(db)


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
async def list_invitations(repo: ProductionDataRepository = Depends(_repo), user: CurrentUser = Depends(get_current_user)) -> list[ProductionMember]:
    return repo.list_invitations(user.uid)


@router.post("/{production_id}/invitation-response", response_model=ProductionMember)
async def respond_to_invitation(production_id: UUID, payload: InvitationResponse, repo: ProductionDataRepository = Depends(_repo), user: CurrentUser = Depends(get_current_user)) -> ProductionMember:
    if payload.decision not in {MembershipStatus.ACCEPTED, MembershipStatus.DECLINED}:
        raise HTTPException(status_code=422, detail="La invitación debe aceptarse o rechazarse.")
    try:
        return repo.respond_to_invitation(production_id, user.uid, payload.decision)
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
async def list_members(production_id: UUID, repo: ProductionDataRepository = Depends(_repo), user: CurrentUser = Depends(get_current_user)) -> list[ProductionMember]:
    try:
        return repo.list_members(production_id, user.uid)
    except ProductionNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Producción no encontrada.") from exc


@router.post("/{production_id}/members", response_model=ProductionMember, status_code=status.HTTP_201_CREATED)
async def add_member(production_id: UUID, payload: ProductionMemberCreate, repo: ProductionDataRepository = Depends(_repo), user: CurrentUser = Depends(get_current_user)) -> ProductionMember:
    try:
        return repo.add_member(production_id, payload, user.uid)
    except ProductionNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Producción no encontrada.") from exc
    except ProductionPermissionError as exc:
        raise HTTPException(status_code=403, detail="Solo el productor puede gestionar el equipo.") from exc
