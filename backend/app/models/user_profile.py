"""Public contracts for FrameFlow user profiles and directory search."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class UserProfileUpdate(BaseModel):
    display_name: str = Field(min_length=2, max_length=80)
    username: str = Field(min_length=3, max_length=30)

    @field_validator("display_name", "username", mode="before")
    @classmethod
    def strip_values(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class UserProfile(BaseModel):
    uid: str
    username: str
    display_name: str
    photo_url: str | None = None
    has_custom_avatar: bool = False
    created_at: datetime
    updated_at: datetime
