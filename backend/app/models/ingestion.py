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
        examples=["Remove the microphone and soften the window glare."],
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
            "true when the note requires actual VFX, color, sound, or editorial work. "
            "false for logistics, catering, transportation, scheduling, congratulations, "
            "conversations unrelated to post-production, or any request that does not "
            "involve VFX, color, sound, or editorial work."
        )
    )
    department: Department | None = Field(
        default=None,
        description="Primary department. Required when requires_postproduction is true.",
    )
    priority: Priority | None = Field(
        default=None,
        description="Priority based on delivery impact. Required when requires_postproduction is true.",
    )
    ai_rationale: str = Field(
        description=(
            "Brief explanation in English. "
            "When a frame is analyzed, state whether the decision is based "
            "on the NOTE, the FRAME, or BOTH."
        )
    )
    rejection_reason: str | None = Field(
        default=None,
        description=(
            "Specific reason why the note does not require post-production. "
            "Only present when requires_postproduction is false."
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
