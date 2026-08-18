from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.models.ticket import Ticket, TicketCreate, TicketReview
from app.services.ticket_store import TicketNotFoundError, ticket_store


router = APIRouter(prefix="/tickets", tags=["Tickets"])


@router.post("", response_model=Ticket, status_code=status.HTTP_201_CREATED)
async def create_ticket(payload: TicketCreate) -> Ticket:
    """Crea un ticket que queda pendiente de aprobación humana."""
    return ticket_store.create(payload)


@router.get("", response_model=list[Ticket])
async def list_tickets() -> list[Ticket]:
    """Devuelve los tickets para las columnas del tablero Kanban."""
    return ticket_store.list()


@router.patch("/{ticket_id}/review", response_model=Ticket)
async def review_ticket(ticket_id: UUID, review: TicketReview) -> Ticket:
    """Registra la aprobación, edición o rechazo del supervisor."""
    try:
        return ticket_store.review(ticket_id, review)
    except TicketNotFoundError as error:
        raise HTTPException(status_code=404, detail="Ticket no encontrado") from error
