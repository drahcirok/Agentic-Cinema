from pydantic import BaseModel, Field

from app.models.ticket import Department, Priority


class DirectorNoteIngestion(BaseModel):
    shot_id: str = Field(min_length=1, max_length=64, examples=["SC03-SH014"])
    director_note: str = Field(min_length=1, examples=["Eliminar el micrófono y suavizar el brillo de la ventana."])


class GeminiClassification(BaseModel):
    department: Department = Field(description="Departamento principal responsable de la tarea.")
    priority: Priority = Field(description="Prioridad según impacto en la entrega y continuidad visual.")
    ai_rationale: str = Field(description="Razón breve y específica de la clasificación.")
