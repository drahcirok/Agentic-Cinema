from datetime import datetime
from uuid import UUID

from app.models.ticket import ReviewDecision, Ticket, TicketCreate, TicketReview, TicketStatus


class TicketNotFoundError(Exception):
    """The requested ticket does not exist in the current store."""


class TicketStore:
    """Temporary in-memory store that can be replaced with a database later."""

    def __init__(self) -> None:
        self._tickets: dict[UUID, Ticket] = {}

    def create(self, payload: TicketCreate) -> Ticket:
        ticket = Ticket(**payload.model_dump())
        self._tickets[ticket.id] = ticket
        return ticket

    def list(self) -> list[Ticket]:
        return sorted(self._tickets.values(), key=lambda ticket: ticket.created_at, reverse=True)

    def review(self, ticket_id: UUID, review: TicketReview) -> Ticket:
        ticket = self._tickets.get(ticket_id)
        if ticket is None:
            raise TicketNotFoundError

        if review.department is not None:
            ticket.department = review.department
        if review.priority is not None:
            ticket.priority = review.priority
        if review.supervisor_note is not None:
            ticket.supervisor_note = review.supervisor_note

        if review.decision is ReviewDecision.APPROVE:
            ticket.status = TicketStatus.APPROVED
        elif review.decision is ReviewDecision.REJECT:
            ticket.status = TicketStatus.REJECTED
        else:
            ticket.status = TicketStatus.PENDING_REVIEW

        ticket.updated_at = datetime.utcnow()
        return ticket


ticket_store = TicketStore()
