from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.ingestion import router as ingestion_router
from app.api.tickets import router as tickets_router
from app.core.config import settings
from app.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Validate storage and initialise SQLite only for local development."""
    settings.validate_ticket_storage()
    if not settings.is_firestore:
        init_db()
    yield


app = FastAPI(
    title="FrameFlow API",
    description="API de orquestación para postproducción y VFX.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tickets_router, prefix="/api/v1")
app.include_router(ingestion_router, prefix="/api/v1")


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Confirma que el servicio está disponible."""
    return {"status": "ok", "service": "frameflow-backend"}
