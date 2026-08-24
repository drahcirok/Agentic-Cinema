from pydantic import BaseModel, Field

from app.models.ticket import Department, Priority

# MIME types accepted for optional frame uploads.
ALLOWED_IMAGE_MIME_TYPES: frozenset[str] = frozenset(
    {"image/jpeg", "image/png", "image/webp"}
)

# Maximum accepted image size in bytes (10 MiB).
MAX_IMAGE_SIZE_BYTES: int = 10 * 1024 * 1024


class DirectorNoteIngestion(BaseModel):
    """Legacy JSON body — kept so existing JSON callers still work."""

    shot_id: str = Field(min_length=1, max_length=64, examples=["SC03-SH014"])
    director_note: str = Field(
        min_length=1,
        examples=["Eliminar el micrófono y suavizar el brillo de la ventana."],
    )


class GeminiClassification(BaseModel):
    department: Department = Field(description="Departamento principal responsable de la tarea.")
    priority: Priority = Field(description="Prioridad según impacto en la entrega y continuidad visual.")
    ai_rationale: str = Field(description="Razón breve y específica de la clasificación.")
