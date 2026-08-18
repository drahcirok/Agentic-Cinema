from google import genai
from google.genai import types
import vertexai

from app.core.config import settings
from app.models.ingestion import GeminiClassification
from app.models.ticket import TicketCreate


class GeminiConfigurationError(Exception):
    """Gemini no puede ejecutarse porque falta la configuración requerida."""


class GeminiClassifier:
    def _create_client(self) -> genai.Client:
        if settings.gemini_backend == "vertex_ai":
            if not settings.google_cloud_project:
                raise GeminiConfigurationError("Falta GOOGLE_CLOUD_PROJECT para usar Vertex AI.")
            vertexai.init(project=settings.google_cloud_project, location=settings.google_cloud_location)
            return genai.Client(
                vertexai=True,
                project=settings.google_cloud_project,
                location=settings.google_cloud_location,
            )
        if not settings.gemini_api_key:
            raise GeminiConfigurationError("Falta GEMINI_API_KEY en backend/.env.")
        return genai.Client(api_key=settings.gemini_api_key)

    def classify(self, shot_id: str, director_note: str) -> TicketCreate:
        client = self._create_client()
        prompt = f"""
Eres el Ingestor Analítico de FrameFlow, una herramienta de postproducción cinematográfica.
Analiza esta nota de dirección y clasifícala en exactamente un departamento: vfx, color,
sound o editorial. Asigna prioridad low, medium, high o critical. Explica el motivo en
español, de manera concreta. No ejecutes cambios ni inventes información.

Toma: {shot_id}
Nota del director: {director_note}
""".strip()
        create_ticket_declaration = types.FunctionDeclaration(
            name="route_postproduction_ticket",
            description="Clasifica una nota del director para crear un ticket de postproducción.",
            parameters={
                "type": "object",
                "properties": {
                    "department": {
                        "type": "string",
                        "enum": ["vfx", "color", "sound", "editorial"],
                        "description": "Departamento principal responsable.",
                    },
                    "priority": {
                        "type": "string",
                        "enum": ["low", "medium", "high", "critical"],
                        "description": "Prioridad según impacto en la entrega.",
                    },
                    "ai_rationale": {
                        "type": "string",
                        "description": "Motivo breve y específico de la clasificación en español.",
                    },
                },
                "required": ["department", "priority", "ai_rationale"],
            },
        )
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(function_declarations=[create_ticket_declaration])],
                tool_config=types.ToolConfig(
                    function_calling_config=types.FunctionCallingConfig(
                        mode="ANY",
                        allowed_function_names=["route_postproduction_ticket"],
                    )
                ),
            ),
        )
        function_call = next(
            (
                part.function_call
                for part in response.candidates[0].content.parts
                if part.function_call is not None and part.function_call.name == "route_postproduction_ticket"
            ),
            None,
        )
        if function_call is None:
            raise RuntimeError("Gemini no devolvió la llamada de función esperada.")
        classification = GeminiClassification.model_validate(function_call.args)
        return TicketCreate(shot_id=shot_id, director_note=director_note, **classification.model_dump())


gemini_classifier = GeminiClassifier()
