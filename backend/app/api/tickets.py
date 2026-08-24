from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.ticket import Ticket, TicketCreate, TicketReview
from app.services.ticket_repository import TicketNotFoundError, TicketRepository

router = APIRouter(prefix="/tickets", tags=["Tickets"])


def _repo(db: Session = Depends(get_db)) -> TicketRepository:
    return TicketRepository(db)


@router.post("", response_model=Ticket, status_code=status.HTTP_201_CREATED)
async def create_ticket(
    payload: TicketCreate,
    repo: TicketRepository = Depends(_repo),
) -> Ticket:
    """Crea un ticket que queda pendiente de aprobación humana."""
    return repo.create(payload)


@router.get("", response_model=list[Ticket])
async def list_tickets(repo: TicketRepository = Depends(_repo)) -> list[Ticket]:
    """Devuelve los tickets para las columnas del tablero Kanban."""
    return repo.list()


@router.patch("/{ticket_id}/review", response_model=Ticket)
async def review_ticket(
    ticket_id: UUID,
    review: TicketReview,
    repo: TicketRepository = Depends(_repo),
) -> Ticket:
    """Registra la aprobación, edición o rechazo del supervisor."""
    try:
        return repo.review(ticket_id, review)
    except TicketNotFoundError as error:
        raise HTTPException(status_code=404, detail="Ticket no encontrado") from error
