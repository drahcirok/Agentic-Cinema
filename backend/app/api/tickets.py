from uuid import UUID

from pathlib import Path

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile, status
from fastapi.responses import Response
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
from app.models.production import ProductionRole
from app.models.ticket import QualityDecision, ReviewDecision
from app.services.video_storage import StorageConfigurationError, video_storage
from app.models.notification import NotificationType
from app.services.notification_repository import NotificationDataRepository, create_notification_repository
from app.models.ticket_activity import TicketActivity
from app.services.ticket_activity_repository import TicketActivityDataRepository, create_ticket_activity_repository

router = APIRouter(prefix="/tickets", tags=["Tickets"])


def _repo(db: Session | None = Depends(get_db)) -> TicketDataRepository:
    return create_ticket_repository(db)


def _production_repo(db: Session | None = Depends(get_db)) -> ProductionDataRepository:
    return create_production_repository(db)


def _notification_repo(db: Session | None = Depends(get_db)) -> NotificationDataRepository:
    return create_notification_repository(db)


def _activity_repo(db: Session | None = Depends(get_db)) -> TicketActivityDataRepository:
    return create_ticket_activity_repository(db)


def _require_production_access(production_id: UUID | None, user: CurrentUser, productions: ProductionDataRepository) -> None:
    if production_id is None:
        return
    try:
        productions.list_members(production_id, user.uid)
    except ProductionNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Producción no encontrada o sin acceso.") from exc


def _role_for(production_id: UUID | None, user: CurrentUser, productions: ProductionDataRepository) -> ProductionRole | None:
    if production_id is None:
        return None
    _require_production_access(production_id, user, productions)
    member = next(member for member in productions.list_members(production_id, user.uid) if member.uid == user.uid)
    return member.role


def _require_role(production_id: UUID | None, user: CurrentUser, productions: ProductionDataRepository, allowed: set[ProductionRole]) -> None:
    role = _role_for(production_id, user, productions)
    if role is not None and role not in allowed:
        raise HTTPException(status_code=403, detail="Tu rol no puede realizar esta acción.")


def _validate_artist_assignment(review: TicketReview, production_id: UUID | None, user: CurrentUser, productions: ProductionDataRepository) -> None:
    if review.decision is not ReviewDecision.APPROVE or production_id is None:
        return
    if not review.assigned_to_uid:
        raise HTTPException(status_code=422, detail="Selecciona un artista antes de asignar el ticket.")
    members = productions.list_members(production_id, user.uid)
    artist = next((member for member in members if member.uid == review.assigned_to_uid), None)
    if artist is None or artist.role is not ProductionRole.ARTIST:
        raise HTTPException(status_code=422, detail="El usuario seleccionado no es un artista de esta producción.")


@router.post("", response_model=Ticket, status_code=status.HTTP_201_CREATED)
async def create_ticket(
    payload: TicketCreate,
    repo: TicketDataRepository = Depends(_repo),
    productions: ProductionDataRepository = Depends(_production_repo),
    activities: TicketActivityDataRepository = Depends(_activity_repo),
    user: CurrentUser = Depends(get_current_user),
    x_production_id: UUID | None = Header(default=None),
) -> Ticket:
    """Crea un ticket que queda pendiente de aprobación humana."""
    _require_production_access(x_production_id, user, productions)
    _require_role(x_production_id, user, productions, {ProductionRole.PRODUCER, ProductionRole.SUPERVISOR})
    ticket = repo.create(payload, user.uid, x_production_id)
    activities.record(ticket.id, x_production_id, user.uid, user.name, "Ticket creado", "Creado manualmente para revisión.")
    return ticket


@router.get("", response_model=list[Ticket])
async def list_tickets(
    repo: TicketDataRepository = Depends(_repo),
    productions: ProductionDataRepository = Depends(_production_repo),
    user: CurrentUser = Depends(get_current_user),
    x_production_id: UUID | None = Header(default=None),
) -> list[Ticket]:
    """Devuelve los tickets para las columnas del tablero Kanban."""
    role = _role_for(x_production_id, user, productions)
    tickets = repo.list(user.uid, x_production_id)
    return [ticket for ticket in tickets if role is not ProductionRole.ARTIST or ticket.assigned_to_uid == user.uid]


@router.patch("/{ticket_id}/review", response_model=Ticket)
async def review_ticket(
    ticket_id: UUID,
    review: TicketReview,
    repo: TicketDataRepository = Depends(_repo),
    productions: ProductionDataRepository = Depends(_production_repo),
    notifications: NotificationDataRepository = Depends(_notification_repo),
    activities: TicketActivityDataRepository = Depends(_activity_repo),
    user: CurrentUser = Depends(get_current_user),
    x_production_id: UUID | None = Header(default=None),
) -> Ticket:
    """Registra la aprobación, edición o rechazo del supervisor."""
    try:
        _require_production_access(x_production_id, user, productions)
        _require_role(x_production_id, user, productions, {ProductionRole.PRODUCER, ProductionRole.SUPERVISOR})
        _validate_artist_assignment(review, x_production_id, user, productions)
        ticket = repo.review(ticket_id, review, user.uid, x_production_id)
        if review.decision is ReviewDecision.APPROVE and ticket.assigned_to_uid:
            notifications.create(ticket.assigned_to_uid, NotificationType.TASK_ASSIGNED, "Nueva tarea asignada", f"{ticket.shot_id}: tienes una tarea de {ticket.department.upper()} asignada.", x_production_id, ticket.id)
            activities.record(ticket.id, x_production_id, user.uid, user.name, "Tarea asignada", f"Asignada a {ticket.assigned_to_name or ticket.assigned_to_uid}.")
        elif review.decision is ReviewDecision.REJECT:
            activities.record(ticket.id, x_production_id, user.uid, user.name, "Ticket rechazado", review.supervisor_note)
        else:
            activities.record(ticket.id, x_production_id, user.uid, user.name, "Ticket enviado a edición", review.supervisor_note)
        return ticket
    except TicketNotFoundError as error:
        raise HTTPException(status_code=404, detail="Ticket no encontrado") from error


@router.patch("/{ticket_id}/work", response_model=Ticket)
async def update_artist_work(
    ticket_id: UUID,
    update: TicketWorkUpdate,
    repo: TicketDataRepository = Depends(_repo),
    productions: ProductionDataRepository = Depends(_production_repo),
    notifications: NotificationDataRepository = Depends(_notification_repo),
    activities: TicketActivityDataRepository = Depends(_activity_repo),
    user: CurrentUser = Depends(get_current_user),
    x_production_id: UUID | None = Header(default=None),
) -> Ticket:
    """Registra el avance del artista: en proceso o listo para QC."""
    try:
        _require_production_access(x_production_id, user, productions)
        _require_role(x_production_id, user, productions, {ProductionRole.ARTIST})
        visible = repo.list(user.uid, x_production_id)
        if not any(ticket.id == ticket_id and ticket.assigned_to_uid == user.uid for ticket in visible):
            raise HTTPException(status_code=403, detail="Esta tarea no está asignada a tu usuario.")
        ticket = repo.update_work(ticket_id, update, user.uid, x_production_id)
        if update.status is not None and str(update.status) == "ready_for_qc" and x_production_id:
            for member in productions.list_members(x_production_id, user.uid):
                if member.role in {ProductionRole.PRODUCER, ProductionRole.SUPERVISOR}:
                    notifications.create(member.uid, NotificationType.QC_READY, "Entrega lista para QC", f"{ticket.shot_id} fue enviada a control de calidad.", x_production_id, ticket.id)
            activities.record(ticket.id, x_production_id, user.uid, user.name, "Entrega enviada a QC", update.artist_note)
        elif update.status is not None:
            activities.record(ticket.id, x_production_id, user.uid, user.name, "Trabajo iniciado")
        return ticket
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
    notifications: NotificationDataRepository = Depends(_notification_repo),
    activities: TicketActivityDataRepository = Depends(_activity_repo),
    user: CurrentUser = Depends(get_current_user),
    x_production_id: UUID | None = Header(default=None),
) -> Ticket:
    """El supervisor completa o devuelve una tarea lista para QC."""
    try:
        _require_production_access(x_production_id, user, productions)
        _require_role(x_production_id, user, productions, {ProductionRole.PRODUCER, ProductionRole.SUPERVISOR})
        ticket = repo.quality_review(ticket_id, review, user.uid, x_production_id)
        if ticket.assigned_to_uid:
            kind = NotificationType.QC_COMPLETED if review.decision is QualityDecision.APPROVE else NotificationType.QC_RETURNED
            title = "Tarea aprobada en QC" if review.decision is QualityDecision.APPROVE else "Tarea devuelta para corrección"
            notifications.create(ticket.assigned_to_uid, kind, title, f"{ticket.shot_id}: {review.supervisor_feedback or 'Revisa el estado de tu tarea.'}", x_production_id, ticket.id)
        activities.record(ticket.id, x_production_id, user.uid, user.name, "QC aprobado" if review.decision is QualityDecision.APPROVE else "Devuelta para corrección", review.supervisor_feedback)
        return ticket
    except TicketNotFoundError as error:
        raise HTTPException(status_code=404, detail="Ticket no encontrado") from error
    except TicketTransitionError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/{ticket_id}/evidence", response_model=Ticket)
async def upload_ticket_evidence(
    ticket_id: UUID,
    evidence: UploadFile = File(...),
    repo: TicketDataRepository = Depends(_repo),
    productions: ProductionDataRepository = Depends(_production_repo),
    activities: TicketActivityDataRepository = Depends(_activity_repo),
    user: CurrentUser = Depends(get_current_user),
    x_production_id: UUID | None = Header(default=None),
) -> Ticket:
    """Attach an optional, small private image or PDF to an artist's delivery."""
    _require_production_access(x_production_id, user, productions)
    _require_role(x_production_id, user, productions, {ProductionRole.ARTIST})
    visible = repo.list(user.uid, x_production_id)
    current_ticket = next((ticket for ticket in visible if ticket.id == ticket_id and ticket.assigned_to_uid == user.uid), None)
    if current_ticket is None:
        raise HTTPException(status_code=403, detail="Esta tarea no está asignada a tu usuario.")

    content_type = evidence.content_type or ""
    extension = Path(evidence.filename or "evidence").suffix.lstrip(".") or "bin"
    data = await evidence.read()
    try:
        gs_uri = video_storage.upload_evidence(data, content_type, extension)
        ticket = repo.attach_evidence(
            ticket_id,
            gs_uri,
            Path(evidence.filename or "evidencia").name[:255],
            content_type,
            user.uid,
            x_production_id,
        )
        if current_ticket.evidence_gcs_uri and current_ticket.evidence_gcs_uri != gs_uri:
            video_storage.delete_object(current_ticket.evidence_gcs_uri)
        action = "Evidencia reemplazada" if current_ticket.evidence_gcs_uri else "Evidencia adjuntada"
        activities.record(ticket.id, x_production_id, user.uid, user.name, action, ticket.evidence_name)
        return ticket
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except StorageConfigurationError as error:
        raise HTTPException(status_code=503, detail="No se pudo preparar el almacenamiento de evidencia.") from error
    except TicketNotFoundError as error:
        raise HTTPException(status_code=404, detail="Ticket no encontrado") from error
    except TicketTransitionError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.delete("/{ticket_id}/evidence", response_model=Ticket)
async def remove_ticket_evidence(
    ticket_id: UUID,
    repo: TicketDataRepository = Depends(_repo),
    productions: ProductionDataRepository = Depends(_production_repo),
    activities: TicketActivityDataRepository = Depends(_activity_repo),
    user: CurrentUser = Depends(get_current_user),
    x_production_id: UUID | None = Header(default=None),
) -> Ticket:
    """Remove optional evidence while an artist is still working on the task."""
    _require_production_access(x_production_id, user, productions)
    _require_role(x_production_id, user, productions, {ProductionRole.ARTIST})
    current_ticket = next(
        (ticket for ticket in repo.list(user.uid, x_production_id) if ticket.id == ticket_id and ticket.assigned_to_uid == user.uid),
        None,
    )
    if current_ticket is None:
        raise HTTPException(status_code=403, detail="Esta tarea no está asignada a tu usuario.")
    if not current_ticket.evidence_gcs_uri:
        raise HTTPException(status_code=404, detail="Este ticket no tiene evidencia adjunta.")
    try:
        ticket = repo.clear_evidence(ticket_id, user.uid, x_production_id)
        video_storage.delete_object(current_ticket.evidence_gcs_uri)
        activities.record(ticket.id, x_production_id, user.uid, user.name, "Evidencia eliminada", current_ticket.evidence_name)
        return ticket
    except TicketNotFoundError as error:
        raise HTTPException(status_code=404, detail="Ticket no encontrado") from error
    except TicketTransitionError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.get("/{ticket_id}/activity", response_model=list[TicketActivity])
async def list_ticket_activity(
    ticket_id: UUID,
    repo: TicketDataRepository = Depends(_repo),
    productions: ProductionDataRepository = Depends(_production_repo),
    activities: TicketActivityDataRepository = Depends(_activity_repo),
    user: CurrentUser = Depends(get_current_user),
    x_production_id: UUID | None = Header(default=None),
) -> list[TicketActivity]:
    """Return the private audit timeline only to people allowed to see the ticket."""
    _require_production_access(x_production_id, user, productions)
    role = _role_for(x_production_id, user, productions)
    ticket = next((item for item in repo.list(user.uid, x_production_id) if item.id == ticket_id), None)
    if ticket is None or (role is ProductionRole.ARTIST and ticket.assigned_to_uid != user.uid):
        raise HTTPException(status_code=404, detail="Ticket no encontrado")
    return activities.list_for_ticket(ticket_id, x_production_id)


@router.get("/{ticket_id}/evidence")
async def download_ticket_evidence(
    ticket_id: UUID,
    repo: TicketDataRepository = Depends(_repo),
    productions: ProductionDataRepository = Depends(_production_repo),
    user: CurrentUser = Depends(get_current_user),
    x_production_id: UUID | None = Header(default=None),
) -> Response:
    """Serve a delivery file only to members allowed to view its production."""
    _require_production_access(x_production_id, user, productions)
    role = _role_for(x_production_id, user, productions)
    ticket = next((item for item in repo.list(user.uid, x_production_id) if item.id == ticket_id), None)
    if ticket is None or (role is ProductionRole.ARTIST and ticket.assigned_to_uid != user.uid):
        raise HTTPException(status_code=404, detail="Evidencia no encontrada")
    if not ticket.evidence_gcs_uri:
        raise HTTPException(status_code=404, detail="Este ticket no tiene evidencia adjunta.")
    try:
        content = video_storage.download_evidence(ticket.evidence_gcs_uri)
    except (StorageConfigurationError, ValueError):
        raise HTTPException(status_code=404, detail="Evidencia no disponible.") from None
    headers = {"Content-Disposition": f'inline; filename="{ticket.evidence_name or "evidencia"}"'}
    return Response(content=content, media_type=ticket.evidence_content_type or "application/octet-stream", headers=headers)
