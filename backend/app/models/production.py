"""Public contracts for productions and their team memberships."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from app.models.ticket import Department


class ProductionRole(StrEnum):
    PRODUCER = "producer"
    SUPERVISOR = "supervisor"
    ARTIST = "artist"


class ProductionCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100, examples=["Nebula - Postproducción"])


class ProductionMemberCreate(BaseModel):
    uid: str = Field(min_length=1, max_length=128)
    role: ProductionRole
    department: Department | None = None
    display_name: str | None = Field(default=None, max_length=120)
    email: str | None = Field(default=None, max_length=254)


class ProductionMember(ProductionMemberCreate):
    production_id: UUID
    created_at: datetime


class Production(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    name: str
    created_by: str
    created_at: datetime
    updated_at: datetime
    current_user_role: ProductionRole | None = None
