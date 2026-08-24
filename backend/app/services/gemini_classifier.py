"""Gemini classifier — text-only and multimodal (text + frame) variants.

Both variants use Function Calling (mode=ANY) so structured output is
guaranteed.  The multimodal path sends the image as Part.from_bytes and
extends the prompt to request explicit attribution (note / frame / both).
"""

from __future__ import annotations

from google import genai
from google.genai import types

from app.core.config import settings
from app.models.ingestion import GeminiClassification
from app.models.ticket import TicketCreate

# ---------------------------------------------------------------------------
# Shared function declaration
# ---------------------------------------------------------------------------

_ROUTE_TICKET_DECLARATION = types.FunctionDeclaration(
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
                "description": (
                    "Motivo breve y específico de la clasificación en español. "
                    "Indica explícitamente si la decisión se basa en la nota del director, "
                    "en el fotograma o en ambos."
                ),
            },
        },
        "required": ["department", "priority", "ai_rationale"],
    },
)

_GENERATE_CONFIG = types.GenerateContentConfig(
    tools=[types.Tool(function_declarations=[_ROUTE_TICKET_DECLARATION])],
    tool_config=types.ToolConfig(
        function_calling_config=types.FunctionCallingConfig(
            mode="ANY",
            allowed_function_names=["route_postproduction_ticket"],
        )
    ),
)

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_TEXT_ONLY_PROMPT = """\
Eres el Ingestor Analítico de FrameFlow, una herramienta de postproducción cinematográfica.
Analiza esta nota de dirección y clasifícala en exactamente un departamento: vfx, color,
sound o editorial. Asigna prioridad low, medium, high o critical. Explica el motivo en
español, de manera concreta. No ejecutes cambios ni inventes información.

Toma: {shot_id}
Nota del director: {director_note}
"""

_MULTIMODAL_PROMPT = """\
Eres el Ingestor Analítico de FrameFlow, una herramienta de postproducción cinematográfica.
Se te proporciona una nota de dirección y el fotograma correspondiente a esa toma.
Analiza ambas fuentes y clasifica la tarea en exactamente un departamento: vfx, color,
sound o editorial. Asigna prioridad low, medium, high o critical.

En el campo ai_rationale, explica en español de forma concreta:
  - si tu clasificación se basa principalmente en la NOTA, en el FOTOGRAMA o en AMBOS,
  - qué elemento concreto de cada fuente influyó en la decisión.

No ejecutes cambios ni inventes información que no esté presente en las fuentes.

Toma: {shot_id}
Nota del director: {director_note}
"""


class GeminiConfigurationError(Exception):
    """Gemini no puede ejecutarse porque falta la configuración requerida."""


class GeminiClassifier:
    def _create_client(self) -> genai.Client:
        """
        Crea el cliente de Gemini según GEMINI_BACKEND:

        - "vertex_ai": usa Application Default Credentials (ADC) automáticamente.
          Requiere GOOGLE_CLOUD_PROJECT y GOOGLE_CLOUD_LOCATION=global.
          No se necesita ninguna API key; las credenciales las provee gcloud ADC
          o el service account del entorno (Cloud Run, GKE, etc.).

        - "developer": usa GEMINI_API_KEY para desarrollo local.
        """
        try:
            settings.validate_vertex_ai()
        except ValueError as exc:
            raise GeminiConfigurationError(str(exc)) from exc

        if settings.is_vertex_ai:
            return genai.Client(
                vertexai=True,
                project=settings.google_cloud_project,
                location=settings.google_cloud_location,
            )

        if not settings.gemini_api_key:
            raise GeminiConfigurationError(
                "GEMINI_BACKEND=developer requiere GEMINI_API_KEY."
            )
        return genai.Client(api_key=settings.gemini_api_key)

    # ------------------------------------------------------------------
    # Internal helper
    # ------------------------------------------------------------------

    def _extract_classification(self, response: types.GenerateContentResponse) -> GeminiClassification:
        """Pull the function-call args out of a Gemini response."""
        function_call = next(
            (
                part.function_call
                for part in response.candidates[0].content.parts
                if part.function_call is not None
                and part.function_call.name == "route_postproduction_ticket"
            ),
            None,
        )
        if function_call is None:
            raise RuntimeError("Gemini no devolvió la llamada de función esperada.")
        return GeminiClassification.model_validate(function_call.args)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def classify(self, shot_id: str, director_note: str) -> TicketCreate:
        """Text-only classification (backward-compatible entry point)."""
        client = self._create_client()
        prompt = _TEXT_ONLY_PROMPT.format(shot_id=shot_id, director_note=director_note).strip()
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
            config=_GENERATE_CONFIG,
        )
        classification = self._extract_classification(response)
        return TicketCreate(shot_id=shot_id, director_note=director_note, **classification.model_dump())

    def classify_with_image(
        self,
        shot_id: str,
        director_note: str,
        image_bytes: bytes,
        mime_type: str,
    ) -> TicketCreate:
        """Multimodal classification: note + raw image bytes.

        The image is sent as an inline Part (no Cloud Storage required).
        ``mime_type`` must be one of the values in ALLOWED_IMAGE_MIME_TYPES.
        """
        client = self._create_client()
        text_prompt = _MULTIMODAL_PROMPT.format(
            shot_id=shot_id, director_note=director_note
        ).strip()
        contents = [
            types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
            types.Part.from_text(text=text_prompt),
        ]
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=contents,
            config=_GENERATE_CONFIG,
        )
        classification = self._extract_classification(response)
        return TicketCreate(shot_id=shot_id, director_note=director_note, **classification.model_dump())


gemini_classifier = GeminiClassifier()
