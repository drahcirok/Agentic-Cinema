from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.ticket import Ticket, TicketCreate, TicketReview
from app.services.ticket_repository import (
    TicketDataRepository,
    TicketNotFoundError,
    create_ticket_repository,
)

router = APIRouter(prefix="/tickets", tags=["Tickets"])


def _repo(db: Session | None = Depends(get_db)) -> TicketDataRepository:
    return create_ticket_repository(db)


@router.post("", response_model=Ticket, status_code=status.HTTP_201_CREATED)
async def create_ticket(
    payload: TicketCreate,
    repo: TicketDataRepository = Depends(_repo),
) -> Ticket:
    """Crea un ticket que queda pendiente de aprobación humana."""
    return repo.create(payload)


@router.get("", response_model=list[Ticket])
async def list_tickets(repo: TicketDataRepository = Depends(_repo)) -> list[Ticket]:
    """Devuelve los tickets para las columnas del tablero Kanban."""
    return repo.list()


@router.patch("/{ticket_id}/review", response_model=Ticket)
async def review_ticket(
    ticket_id: UUID,
    review: TicketReview,
    repo: TicketDataRepository = Depends(_repo),
) -> Ticket:
    """Registra la aprobación, edición o rechazo del supervisor."""
    try:
        return repo.review(ticket_id, review)
    except TicketNotFoundError as error:
        raise HTTPException(status_code=404, detail="Ticket no encontrado") from error
