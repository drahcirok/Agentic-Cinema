"""SQLAlchemy 2.x database configuration for FrameFlow.

The SQLite database file is stored at backend/data/frameflow.db.
The `data/` directory is created automatically if it does not exist.
"""

from __future__ import annotations

from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_HERE = Path(__file__).resolve().parent          # backend/app/
_DATA_DIR = _HERE.parent / "data"                # backend/data/

DATABASE_URL = f"sqlite:///{_DATA_DIR / 'frameflow.db'}"

# ---------------------------------------------------------------------------
# Engine & session factory
# ---------------------------------------------------------------------------

if settings.is_firestore:
    # Cloud Run uses Firestore. Do not create the local data directory or open
    # a SQLite connection: /app is read-only for the unprivileged container
    # user and SQLite would be ephemeral anyway.
    engine = None
    SessionLocal = None
else:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
    )
    SessionLocal = sessionmaker(
        bind=engine,
        autocommit=False,
        autoflush=False,
    )

# ---------------------------------------------------------------------------
# Declarative base (shared by all ORM models)
# ---------------------------------------------------------------------------


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------


def get_db() -> Generator[Session | None, None, None]:
    """Yield SQLite only in local mode; Firestore needs no SQL session."""
    if settings.is_firestore:
        yield None
        return

    assert SessionLocal is not None
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Table initialisation
# ---------------------------------------------------------------------------


def init_db() -> None:
    """Create all tables registered on Base.metadata (idempotent)."""
    if settings.is_firestore:
        return

    # Import models so their Table definitions are registered before create_all.
    import app.models.ticket_record  # noqa: F401
    import app.models.production_record  # noqa: F401

    assert engine is not None
    Base.metadata.create_all(bind=engine)

    # SQLite no aplica ALTER TABLE al añadir columnas mediante create_all().
    # Esta migración pequeña mantiene los datos locales existentes al incorporar
    # owner_id para el aislamiento por supervisor.
    columns = {column["name"] for column in inspect(engine).get_columns("postproduction_tickets")}
    with engine.begin() as connection:
        if "owner_id" not in columns:
            connection.execute(
                text("ALTER TABLE postproduction_tickets ADD COLUMN owner_id VARCHAR(128)")
            )
        if "production_id" not in columns:
            connection.execute(text("ALTER TABLE postproduction_tickets ADD COLUMN production_id VARCHAR(36)"))
        if "artist_note" not in columns:
            connection.execute(text("ALTER TABLE postproduction_tickets ADD COLUMN artist_note TEXT"))
        if "supervisor_feedback" not in columns:
            connection.execute(text("ALTER TABLE postproduction_tickets ADD COLUMN supervisor_feedback TEXT"))
