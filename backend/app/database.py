"""SQLAlchemy 2.x database configuration for FrameFlow.

The SQLite database file is stored at backend/data/frameflow.db.
The `data/` directory is created automatically if it does not exist.
"""

from __future__ import annotations

from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_HERE = Path(__file__).resolve().parent          # backend/app/
_DATA_DIR = _HERE.parent / "data"                # backend/data/
_DATA_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_URL = f"sqlite:///{_DATA_DIR / 'frameflow.db'}"

# ---------------------------------------------------------------------------
# Engine & session factory
# ---------------------------------------------------------------------------

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


def get_db() -> Generator[Session, None, None]:
    """Yield a database session and guarantee it is closed after the request."""
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
    # Import models so their Table definitions are registered before create_all.
    import app.models.ticket_record  # noqa: F401

    Base.metadata.create_all(bind=engine)
