"""Authenticated endpoints for each user's in-app notification inbox."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import CurrentUser, get_current_user
from app.database import get_db
from app.models.notification import Notification
from app.services.notification_repository import NotificationDataRepository, NotificationNotFoundError, create_notification_repository

router = APIRouter(prefix="/notifications", tags=["Notifications"])


def _repo(db: Session | None = Depends(get_db)) -> NotificationDataRepository:
    return create_notification_repository(db)


@router.get("", response_model=list[Notification])
async def list_notifications(repo: NotificationDataRepository = Depends(_repo), user: CurrentUser = Depends(get_current_user)) -> list[Notification]:
    return repo.list_for_user(user.uid)


@router.patch("/read-all", status_code=status.HTTP_204_NO_CONTENT)
async def mark_all_read(repo: NotificationDataRepository = Depends(_repo), user: CurrentUser = Depends(get_current_user)) -> None:
    repo.mark_all_read(user.uid)


@router.patch("/{notification_id}/read", response_model=Notification)
async def mark_read(notification_id: UUID, repo: NotificationDataRepository = Depends(_repo), user: CurrentUser = Depends(get_current_user)) -> Notification:
    try:
        return repo.mark_read(notification_id, user.uid)
    except NotificationNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Notification not found.") from exc
