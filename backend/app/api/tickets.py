from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
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

router = APIRouter(prefix="/tickets", tags=["Tickets"])


def _repo(db: Session | None = Depends(get_db)) -> TicketDataRepository:
    return create_ticket_repository(db)


@router.post("", response_model=Ticket, status_code=status.HTTP_201_CREATED)
async def create_ticket(
    payload: TicketCreate,
    repo: TicketDataRepository = Depends(_repo),
    user: CurrentUser = Depends(get_current_user),
) -> Ticket:
    """Crea un ticket que queda pendiente de aprobación humana."""
    return repo.create(payload, user.uid)


@router.get("", response_model=list[Ticket])
async def list_tickets(
    repo: TicketDataRepository = Depends(_repo),
    user: CurrentUser = Depends(get_current_user),
) -> list[Ticket]:
    """Devuelve los tickets para las columnas del tablero Kanban."""
    return repo.list(user.uid)


@router.patch("/{ticket_id}/review", response_model=Ticket)
async def review_ticket(
    ticket_id: UUID,
    review: TicketReview,
    repo: TicketDataRepository = Depends(_repo),
    user: CurrentUser = Depends(get_current_user),
) -> Ticket:
    """Registra la aprobación, edición o rechazo del supervisor."""
    try:
        return repo.review(ticket_id, review, user.uid)
    except TicketNotFoundError as error:
        raise HTTPException(status_code=404, detail="Ticket no encontrado") from error


@router.patch("/{ticket_id}/work", response_model=Ticket)
async def update_artist_work(
    ticket_id: UUID,
    update: TicketWorkUpdate,
    repo: TicketDataRepository = Depends(_repo),
    user: CurrentUser = Depends(get_current_user),
) -> Ticket:
    """Registra el avance del artista: en proceso o listo para QC."""
    try:
        return repo.update_work(ticket_id, update, user.uid)
    except TicketNotFoundError as error:
        raise HTTPException(status_code=404, detail="Ticket no encontrado") from error
    except TicketTransitionError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.patch("/{ticket_id}/quality-review", response_model=Ticket)
async def quality_review_ticket(
    ticket_id: UUID,
    review: TicketQualityReview,
    repo: TicketDataRepository = Depends(_repo),
    user: CurrentUser = Depends(get_current_user),
) -> Ticket:
    """El supervisor completa o devuelve una tarea lista para QC."""
    try:
        return repo.quality_review(ticket_id, review, user.uid)
    except TicketNotFoundError as error:
        raise HTTPException(status_code=404, detail="Ticket no encontrado") from error
    except TicketTransitionError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
