"""Public contracts for productions and their team memberships."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from app.models.ticket import Department
from app.models.user_profile import UserProfile


class ProductionRole(StrEnum):
    PRODUCER = "producer"
    SUPERVISOR = "supervisor"
    ARTIST = "artist"


class MembershipStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    DECLINED = "declined"


class ProductionCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100, examples=["Nebula - Post-production"])


class ProductionUpdate(BaseModel):
    name: str = Field(min_length=2, max_length=100)


class ProductionMemberCreate(BaseModel):
    uid: str = Field(min_length=1, max_length=128)
    role: ProductionRole
    department: Department | None = None


class InvitationResponse(BaseModel):
    decision: MembershipStatus = Field(description="Only accepted or declined are allowed.")


class ProductionMember(ProductionMemberCreate):
    display_name: str | None = Field(default=None, max_length=120)
    username: str | None = Field(default=None, max_length=30)
    photo_url: str | None = None
    has_custom_avatar: bool = False
    profile_updated_at: datetime | None = None
    production_id: UUID
    created_at: datetime
    membership_status: MembershipStatus = MembershipStatus.ACCEPTED
    production_name: str | None = None
    invited_by_uid: str | None = None
    invited_by: UserProfile | None = None


class Production(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    name: str
    created_by: str
    created_at: datetime
    updated_at: datetime
    current_user_role: ProductionRole | None = None
