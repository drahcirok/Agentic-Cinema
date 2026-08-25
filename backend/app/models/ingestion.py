from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.ticket import Department, Priority

# ---------------------------------------------------------------------------
# Image upload constants (local, inline bytes — used today)
# ---------------------------------------------------------------------------

# MIME types accepted for optional frame uploads.
ALLOWED_IMAGE_MIME_TYPES: frozenset[str] = frozenset(
    {"image/jpeg", "image/png", "image/webp"}
)

# Maximum accepted image size in bytes (10 MiB).
MAX_IMAGE_SIZE_BYTES: int = 10 * 1024 * 1024

# ---------------------------------------------------------------------------
# Video upload constants (Cloud Storage — reserved for future use)
# These mirror the values in app/services/video_storage.py so that the
# endpoint layer can import from a single place without touching the service.
# ---------------------------------------------------------------------------

# MIME types accepted for video uploads.
ALLOWED_VIDEO_MIME_TYPES: frozenset[str] = frozenset({"video/mp4"})

# Maximum accepted video size in bytes (50 MiB).
MAX_VIDEO_SIZE_BYTES: int = 50 * 1024 * 1024


class DirectorNoteIngestion(BaseModel):
    """Legacy JSON body — kept so existing JSON callers still work."""

    shot_id: str = Field(min_length=1, max_length=64, examples=["SC03-SH014"])
    director_note: str = Field(
        min_length=1,
        examples=["Eliminar el micrófono y suavizar el brillo de la ventana."],
    )


class GeminiDecision(BaseModel):
    """Structured output returned by the Gemini function call.

    ``requires_postproduction`` is always present.
    ``department`` and ``priority`` are only present (and only required) when
    ``requires_postproduction`` is ``True``.
    ``rejection_reason`` is only meaningful when ``requires_postproduction`` is ``False``.
    """

    requires_postproduction: bool = Field(
        description=(
            "true si la nota requiere trabajo real de VFX, color, sonido o edición. "
            "false para logística, catering, transporte, horarios, felicitaciones, "
            "conversaciones no relacionadas con postproducción o cualquier pedido "
            "que no implique trabajo de VFX, color, sonido ni edición."
        )
    )
    department: Department | None = Field(
        default=None,
        description="Departamento principal. Obligatorio cuando requires_postproduction es true.",
    )
    priority: Priority | None = Field(
        default=None,
        description="Prioridad según impacto en la entrega. Obligatorio cuando requires_postproduction es true.",
    )
    ai_rationale: str = Field(
        description=(
            "Explicación breve en español. "
            "Cuando se analiza un fotograma, indica si la decisión se basa "
            "en la NOTA, el FOTOGRAMA o AMBOS."
        )
    )
    rejection_reason: str | None = Field(
        default=None,
        description=(
            "Razón específica por la que la nota no requiere postproducción. "
            "Solo presente cuando requires_postproduction es false."
        ),
    )


# Legacy alias — kept so existing code that imports GeminiClassification still compiles.
GeminiClassification = GeminiDecision


class EligibilityRejection(BaseModel):
    """Response body returned with HTTP 200 when Gemini decides the note
    does not require any post-production work.  No ticket is created.
    """

    requires_postproduction: bool = False
    ai_rationale: str
    rejection_reason: str | None = None
