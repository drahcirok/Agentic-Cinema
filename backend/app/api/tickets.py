from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.core.security import CurrentUser, get_current_user
from app.models.ticket import Ticket, TicketCreate, TicketQualityReview, TicketReview, TicketWorkUpdate
from app.services.ticket_repository import (
    TicketDataRepository,
    TicketNotFoundError,
    TicketTransitionError,
    create_ticket_repository,
)
from app.services.production_repository import ProductionDataRepository, ProductionNotFoundError, create_production_repository

router = APIRouter(prefix="/tickets", tags=["Tickets"])


def _repo(db: Session | None = Depends(get_db)) -> TicketDataRepository:
    return create_ticket_repository(db)


def _production_repo(db: Session | None = Depends(get_db)) -> ProductionDataRepository:
    return create_production_repository(db)


def _require_production_access(production_id: UUID | None, user: CurrentUser, productions: ProductionDataRepository) -> None:
    if production_id is None:
        return
    try:
        productions.list_members(production_id, user.uid)
    except ProductionNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Producción no encontrada o sin acceso.") from exc


@router.post("", response_model=Ticket, status_code=status.HTTP_201_CREATED)
async def create_ticket(
    payload: TicketCreate,
    repo: TicketDataRepository = Depends(_repo),
    productions: ProductionDataRepository = Depends(_production_repo),
    user: CurrentUser = Depends(get_current_user),
    x_production_id: UUID | None = Header(default=None),
) -> Ticket:
    """Crea un ticket que queda pendiente de aprobación humana."""
    _require_production_access(x_production_id, user, productions)
    return repo.create(payload, user.uid, x_production_id)


@router.get("", response_model=list[Ticket])
async def list_tickets(
    repo: TicketDataRepository = Depends(_repo),
    productions: ProductionDataRepository = Depends(_production_repo),
    user: CurrentUser = Depends(get_current_user),
    x_production_id: UUID | None = Header(default=None),
) -> list[Ticket]:
    """Devuelve los tickets para las columnas del tablero Kanban."""
    _require_production_access(x_production_id, user, productions)
    return repo.list(user.uid, x_production_id)


@router.patch("/{ticket_id}/review", response_model=Ticket)
async def review_ticket(
    ticket_id: UUID,
    review: TicketReview,
    repo: TicketDataRepository = Depends(_repo),
    productions: ProductionDataRepository = Depends(_production_repo),
    user: CurrentUser = Depends(get_current_user),
    x_production_id: UUID | None = Header(default=None),
) -> Ticket:
    """Registra la aprobación, edición o rechazo del supervisor."""
    try:
        _require_production_access(x_production_id, user, productions)
        return repo.review(ticket_id, review, user.uid, x_production_id)
    except TicketNotFoundError as error:
        raise HTTPException(status_code=404, detail="Ticket no encontrado") from error


@router.patch("/{ticket_id}/work", response_model=Ticket)
async def update_artist_work(
    ticket_id: UUID,
    update: TicketWorkUpdate,
    repo: TicketDataRepository = Depends(_repo),
    productions: ProductionDataRepository = Depends(_production_repo),
    user: CurrentUser = Depends(get_current_user),
    x_production_id: UUID | None = Header(default=None),
) -> Ticket:
    """Registra el avance del artista: en proceso o listo para QC."""
    try:
        _require_production_access(x_production_id, user, productions)
        return repo.update_work(ticket_id, update, user.uid, x_production_id)
    except TicketNotFoundError as error:
        raise HTTPException(status_code=404, detail="Ticket no encontrado") from error
    except TicketTransitionError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.patch("/{ticket_id}/quality-review", response_model=Ticket)
async def quality_review_ticket(
    ticket_id: UUID,
    review: TicketQualityReview,
    repo: TicketDataRepository = Depends(_repo),
    productions: ProductionDataRepository = Depends(_production_repo),
    user: CurrentUser = Depends(get_current_user),
    x_production_id: UUID | None = Header(default=None),
) -> Ticket:
    """El supervisor completa o devuelve una tarea lista para QC."""
    try:
        _require_production_access(x_production_id, user, productions)
        return repo.quality_review(ticket_id, review, user.uid, x_production_id)
    except TicketNotFoundError as error:
        raise HTTPException(status_code=404, detail="Ticket no encontrado") from error
    except TicketTransitionError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
