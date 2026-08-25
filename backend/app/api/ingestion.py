"""Ingestion endpoint — accepts application/json, multipart/form-data and
application/x-www-form-urlencoded.

Supported Content-Type values
------------------------------
application/json
    Body: {"shot_id": "...", "director_note": "..."}
    Text-only classify path.

multipart/form-data
    Fields: shot_id (str, required), director_note (str, required)
    Files (mutually exclusive — at most one):
        frame (optional) — image .jpg/.png/.webp, max 10 MiB → classify_with_image()
        video (optional) — video/mp4, max 50 MiB             → classify_with_video()
    Sending both frame and video in the same request → 422.

application/x-www-form-urlencoded
    Same as multipart but without binary support → text-only classify().

Anything else → 415 Unsupported Media Type.

Response codes
--------------
201  Ticket created     — body: Ticket (requires_postproduction was True)
200  Not required       — body: EligibilityRejection (no SQLite record written)
400  Malformed request
413  File too large
415  Unsupported media type (request CT or uploaded file CT)
422  Validation error (missing fields, frame+video together, empty file)
503  Storage/Gemini not configured
502  Gemini or Storage unrecoverable error
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.ingestion import (
    ALLOWED_IMAGE_MIME_TYPES,
    ALLOWED_VIDEO_MIME_TYPES,
    MAX_IMAGE_SIZE_BYTES,
    MAX_VIDEO_SIZE_BYTES,
    DirectorNoteIngestion,
    EligibilityRejection,
)
from app.models.ticket import Ticket, TicketCreate
from app.services.gemini_classifier import GeminiConfigurationError, gemini_classifier
from app.services.ticket_repository import TicketDataRepository, create_ticket_repository
from app.services.video_storage import StorageConfigurationError, video_storage

_log = logging.getLogger(__name__)

router = APIRouter(prefix="/ingestion", tags=["Gemini ingestion"])

# Content-type → MIME type normalisation (browsers sometimes send "image/jpg").
_MIME_ALIASES: dict[str, str] = {"image/jpg": "image/jpeg"}


def _repo(db: Session | None = Depends(get_db)) -> TicketDataRepository:
    return create_ticket_repository(db)


def _media_type(request: Request) -> str:
    """Return the bare media type without charset/boundary parameters."""
    ct = request.headers.get("content-type", "")
    return ct.split(";")[0].strip().lower()


@router.post(
    "/director-notes",
    response_model=None,
    status_code=status.HTTP_201_CREATED,
)
async def ingest_director_note(
    request: Request,
    repo: TicketDataRepository = Depends(_repo),
) -> JSONResponse:
    """Evalúa si la nota requiere postproducción y, si es así, crea el ticket.

    Acepta ``application/json``, ``multipart/form-data`` y
    ``application/x-www-form-urlencoded``.  En multipart se puede adjuntar un
    fotograma *o* un video MP4 (no ambos).

    Respuestas:
    * **201** — requiere postproducción; cuerpo: ``Ticket``.
    * **200** — no requiere postproducción; cuerpo: ``EligibilityRejection``.
      No se escribe ningún registro en SQLite.
    """
    mt = _media_type(request)

    # ------------------------------------------------------------------
    # Branch A — application/json (text-only)
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
        image_mime: str | None = None
        video_bytes: bytes | None = None
        video_mime: str | None = None

    # ------------------------------------------------------------------
    # Branch B — multipart/form-data or application/x-www-form-urlencoded
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

        frame_field = form.get("frame")
        video_field = form.get("video")

        has_frame = frame_field is not None and hasattr(frame_field, "read")
        has_video = video_field is not None and hasattr(video_field, "read")

        # Mutual exclusion — frame and video cannot be sent together.
        if has_frame and has_video:
            raise HTTPException(
                status_code=422,
                detail=(
                    "No se pueden adjuntar 'frame' y 'video' en la misma solicitud. "
                    "Envía solo uno a la vez."
                ),
            )

        image_bytes = None
        image_mime = None
        video_bytes = None
        video_mime = None

        # ---- Frame ----
        if has_frame:
            raw_ct = (getattr(frame_field, "content_type", None) or "").lower().split(";")[0].strip()
            image_mime = _MIME_ALIASES.get(raw_ct, raw_ct)

            if image_mime not in ALLOWED_IMAGE_MIME_TYPES:
                raise HTTPException(
                    status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                    detail=(
                        f"Tipo de imagen no permitido: '{image_mime}'. "
                        f"Se aceptan: {', '.join(sorted(ALLOWED_IMAGE_MIME_TYPES))}."
                    ),
                )

            image_bytes = await frame_field.read()

            if len(image_bytes) == 0:
                raise HTTPException(status_code=422, detail="El fotograma adjunto está vacío.")

            if len(image_bytes) > MAX_IMAGE_SIZE_BYTES:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=(
                        f"El fotograma supera el límite de "
                        f"{MAX_IMAGE_SIZE_BYTES // (1024 * 1024)} MiB."
                    ),
                )

        # ---- Video ----
        if has_video:
            raw_ct = (getattr(video_field, "content_type", None) or "").lower().split(";")[0].strip()
            video_mime = raw_ct  # no alias needed for video

            if video_mime not in ALLOWED_VIDEO_MIME_TYPES:
                raise HTTPException(
                    status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                    detail=(
                        f"Tipo de video no permitido: '{video_mime}'. "
                        f"Se aceptan: {', '.join(sorted(ALLOWED_VIDEO_MIME_TYPES))}."
                    ),
                )

            video_bytes = await video_field.read()

            if len(video_bytes) == 0:
                raise HTTPException(status_code=422, detail="El video adjunto está vacío.")

            if len(video_bytes) > MAX_VIDEO_SIZE_BYTES:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=(
                        f"El video supera el límite de "
                        f"{MAX_VIDEO_SIZE_BYTES // (1024 * 1024)} MiB."
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
    # Evaluate eligibility + classify
    # ------------------------------------------------------------------
    if video_bytes is not None and video_mime is not None:
        # Video path: upload to GCS, call Gemini with gs:// URI, always clean up.
        gs_uri: str | None = None
        try:
            try:
                gs_uri = video_storage.upload_video(video_bytes, video_mime)
            except StorageConfigurationError as exc:
                raise HTTPException(
                    status_code=503,
                    detail=f"Configuración de Cloud Storage incompleta: {exc}",
                ) from exc
            except Exception as exc:
                raise HTTPException(
                    status_code=502,
                    detail="No se pudo subir el video a Cloud Storage.",
                ) from exc

            try:
                result = gemini_classifier.classify_with_video(
                    shot_id, director_note, gs_uri, video_mime
                )
            except GeminiConfigurationError as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from exc
            except Exception as exc:
                raise HTTPException(
                    status_code=502,
                    detail="Gemini no pudo analizar el video.",
                ) from exc

        finally:
            # Always attempt cleanup, even when Gemini or the upload raised.
            # Wrap in try/except so a cleanup failure can never:
            #   • replace a valid 201 / 200 response already computed, or
            #   • mask the original Gemini / upload HTTPException.
            # delete_object() is itself best-effort (logs and swallows all
            # errors internally), but we add a second guard here so that any
            # unexpected propagation is still contained at this layer.
            if gs_uri is not None:
                try:
                    video_storage.delete_object(gs_uri)
                except Exception as _cleanup_exc:  # pragma: no cover
                    _log.warning(
                        "Cleanup guard: delete_object raised unexpectedly "
                        "(type: %s, object path hidden). "
                        "Primary response/exception is preserved.",
                        type(_cleanup_exc).__name__,
                    )

    elif image_bytes is not None and image_mime is not None:
        try:
            result = gemini_classifier.classify_with_image(
                shot_id, director_note, image_bytes, image_mime
            )
        except GeminiConfigurationError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
        except Exception as error:
            raise HTTPException(status_code=502, detail="Gemini no pudo analizar la nota.") from error

    else:
        try:
            result = gemini_classifier.classify(shot_id, director_note)
        except GeminiConfigurationError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
        except Exception as error:
            raise HTTPException(status_code=502, detail="Gemini no pudo analizar la nota.") from error

    # ------------------------------------------------------------------
    # Route the result
    # ------------------------------------------------------------------
    if isinstance(result, EligibilityRejection):
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=result.model_dump(),
        )

    ticket = repo.create(result)
    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=Ticket.model_validate(ticket).model_dump(mode="json"),
    )
