"""SQLAlchemy persistence model for local FrameFlow profiles."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UserProfileRecord(Base):
    __tablename__ = "user_profiles"

    uid: Mapped[str] = mapped_column(String(128), primary_key=True)
    username: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    photo_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    avatar_gcs_uri: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
