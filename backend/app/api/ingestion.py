"""Ingestion endpoint — accepts both application/json and multipart/form-data.

Supported Content-Type values:
    application/json
        Body: {"shot_id": "...", "director_note": "..."}
        Validated via DirectorNoteIngestion.  No image — text classify only.

    multipart/form-data
        Fields: shot_id (str, required), director_note (str, required)
        File:   frame (optional) — .jpg / .jpeg / .png / .webp, max 10 MiB
        When frame is present → multimodal classify_with_image().
        When frame is absent  → text-only classify() (same as JSON path).

    Anything else → 415 Unsupported Media Type.

The file is never persisted; it is only read into memory for the duration
of the request and forwarded to Gemini as Part.from_bytes.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.ingestion import (
    ALLOWED_IMAGE_MIME_TYPES,
    MAX_IMAGE_SIZE_BYTES,
    DirectorNoteIngestion,
)
from app.models.ticket import Ticket
from app.services.gemini_classifier import GeminiConfigurationError, gemini_classifier
from app.services.ticket_repository import TicketRepository

router = APIRouter(prefix="/ingestion", tags=["Gemini ingestion"])

# Content-type → MIME type normalisation for browsers that send
# "image/jpg" instead of the canonical "image/jpeg".
_MIME_ALIASES: dict[str, str] = {"image/jpg": "image/jpeg"}


def _repo(db: Session = Depends(get_db)) -> TicketRepository:
    return TicketRepository(db)


def _media_type(request: Request) -> str:
    """Return the bare media type (without parameters such as charset/boundary)."""
    ct = request.headers.get("content-type", "")
    return ct.split(";")[0].strip().lower()


@router.post("/director-notes", response_model=Ticket, status_code=status.HTTP_201_CREATED)
async def ingest_director_note(
    request: Request,
    repo: TicketRepository = Depends(_repo),
) -> Ticket:
    """Clasifica una nota (y opcionalmente un fotograma) mediante Gemini y crea
    un ticket pendiente de revisión humana.

    Acepta dos contratos según el ``Content-Type`` de la petición:

    * **application/json** — ``{"shot_id": "...", "director_note": "..."}``
      Clasificación solo por texto.

    * **multipart/form-data** — campos ``shot_id``, ``director_note`` y
      fichero ``frame`` opcional (.jpg / .png / .webp, máx. 10 MiB).
      Con imagen → clasificación multimodal; sin imagen → solo texto.
    """
    mt = _media_type(request)

    # ------------------------------------------------------------------
    # Branch A — application/json (original contract, text-only)
    # ------------------------------------------------------------------
    if mt == "application/json":
        try:
            raw = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="JSON inválido.")

        try:
            payload = DirectorNoteIngestion.model_validate(raw)
        except Exception as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        shot_id = payload.shot_id
        director_note = payload.director_note
        image_bytes: bytes | None = None
        mime_type: str | None = None

    # ------------------------------------------------------------------
    # Branch B — multipart/form-data or application/x-www-form-urlencoded
    #
    # Both are form-based.  URL-encoded requests can only carry text fields
    # (no binary file), so they always take the text-only classify() path.
    # multipart/form-data additionally supports an optional ``frame`` file.
    # ------------------------------------------------------------------
    elif mt in ("multipart/form-data", "application/x-www-form-urlencoded"):
        try:
            form = await request.form()
        except Exception as exc:
            raise HTTPException(status_code=400, detail="Formulario inválido.") from exc

        shot_id_raw = form.get("shot_id")
        director_note_raw = form.get("director_note")

        if not shot_id_raw or not isinstance(shot_id_raw, str):
            raise HTTPException(status_code=422, detail="El campo 'shot_id' es obligatorio.")
        if not director_note_raw or not isinstance(director_note_raw, str):
            raise HTTPException(status_code=422, detail="El campo 'director_note' es obligatorio.")

        shot_id = shot_id_raw.strip()
        director_note = director_note_raw.strip()

        if not (1 <= len(shot_id) <= 64):
            raise HTTPException(
                status_code=422,
                detail="'shot_id' debe tener entre 1 y 64 caracteres.",
            )
        if len(director_note) < 1:
            raise HTTPException(status_code=422, detail="'director_note' no puede estar vacío.")

        frame = form.get("frame")
        image_bytes = None
        mime_type = None

        if frame is not None and hasattr(frame, "read"):
            # Normalise content type
            raw_ct = (getattr(frame, "content_type", None) or "").lower().split(";")[0].strip()
            mime_type = _MIME_ALIASES.get(raw_ct, raw_ct)

            if mime_type not in ALLOWED_IMAGE_MIME_TYPES:
                raise HTTPException(
                    status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                    detail=(
                        f"Tipo de archivo no permitido: '{mime_type}'. "
                        f"Se aceptan: {', '.join(sorted(ALLOWED_IMAGE_MIME_TYPES))}."
                    ),
                )

            image_bytes = await frame.read()

            if len(image_bytes) > MAX_IMAGE_SIZE_BYTES:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=(
                        f"El archivo supera el límite de "
                        f"{MAX_IMAGE_SIZE_BYTES // (1024 * 1024)} MiB."
                    ),
                )

    # ------------------------------------------------------------------
    # Unsupported Content-Type
    # ------------------------------------------------------------------
    else:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                f"Content-Type no soportado: '{mt}'. "
                "Use 'application/json' o 'multipart/form-data'."
            ),
        )

    # ------------------------------------------------------------------
    # Classify and persist (shared by both branches)
    # ------------------------------------------------------------------
    try:
        if image_bytes is not None and mime_type is not None:
            ticket_payload = gemini_classifier.classify_with_image(
                shot_id, director_note, image_bytes, mime_type
            )
        else:
            ticket_payload = gemini_classifier.classify(shot_id, director_note)
    except GeminiConfigurationError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=502, detail="Gemini no pudo analizar la nota.") from error

    return repo.create(ticket_payload)
