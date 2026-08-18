from fastapi import APIRouter, HTTPException, status

from app.models.ingestion import DirectorNoteIngestion
from app.models.ticket import Ticket
from app.services.gemini_classifier import GeminiConfigurationError, gemini_classifier
from app.services.ticket_store import ticket_store


router = APIRouter(prefix="/ingestion", tags=["Gemini ingestion"])


@router.post("/director-notes", response_model=Ticket, status_code=status.HTTP_201_CREATED)
async def ingest_director_note(payload: DirectorNoteIngestion) -> Ticket:
    """Clasifica una nota mediante Gemini y crea un ticket pendiente de revisión humana."""
    try:
        ticket_payload = gemini_classifier.classify(payload.shot_id, payload.director_note)
    except GeminiConfigurationError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=502, detail="Gemini no pudo analizar la nota.") from error
    return ticket_store.create(ticket_payload)
