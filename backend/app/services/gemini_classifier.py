"""Gemini classifier — eligibility check + classification in a single call.

The classifier uses a single Function Calling declaration that returns:
  - requires_postproduction (bool)      — always present
  - department / priority               — present only when requires_postproduction=True
  - ai_rationale (str)                  — always present
  - rejection_reason (str | None)       — present when requires_postproduction=False

Both classify() and classify_with_image() return either:
  - TicketCreate          — when the note requires post-production work
  - EligibilityRejection  — when it does not (no SQLite record created)

The multimodal path sends image bytes as Part.from_bytes alongside the text
prompt and extends ai_rationale to mention whether the decision was based on
the note, the frame, or both.
"""

from __future__ import annotations

from google import genai
from google.genai import types

from app.core.config import settings
from app.models.ingestion import EligibilityRejection, GeminiDecision
from app.models.ticket import TicketCreate

# ---------------------------------------------------------------------------
# Function declaration — single declaration used by all classify paths
# ---------------------------------------------------------------------------

_EVALUATE_DECLARATION = types.FunctionDeclaration(
    name="evaluate_postproduction_request",
    description=(
        "Evalúa si una nota del director requiere trabajo real de postproducción. "
        "Si lo requiere, clasifica el departamento y la prioridad. "
        "Si no, explica por qué no aplica."
    ),
    parameters={
        "type": "object",
        "properties": {
            "requires_postproduction": {
                "type": "boolean",
                "description": (
                    "true si la nota exige trabajo de VFX, color, sonido o edición. "
                    "false para notas de logística, catering, transporte, horarios, "
                    "felicitaciones, conversaciones no relacionadas o cualquier pedido "
                    "que no implique trabajo real de postproducción."
                ),
            },
            "department": {
                "type": "string",
                "enum": ["vfx", "color", "sound", "editorial"],
                "description": (
                    "Departamento principal responsable. "
                    "Obligatorio cuando requires_postproduction es true. "
                    "Omite este campo cuando requires_postproduction es false."
                ),
            },
            "priority": {
                "type": "string",
                "enum": ["low", "medium", "high", "critical"],
                "description": (
                    "Prioridad según impacto en la entrega. "
                    "Obligatorio cuando requires_postproduction es true. "
                    "Omite este campo cuando requires_postproduction es false."
                ),
            },
            "ai_rationale": {
                "type": "string",
                "description": (
                    "Explicación breve y concreta en español. "
                    "Indica explícitamente si la decisión se basa en la NOTA, "
                    "el FOTOGRAMA, el VIDEO o en una combinación de ellos."
                ),
            },
            "rejection_reason": {
                "type": "string",
                "description": (
                    "Categoría de rechazo cuando requires_postproduction es false. "
                    "Ejemplos: 'logística', 'catering', 'transporte', 'horarios', "
                    "'felicitaciones', 'asunto no relacionado con postproducción'. "
                    "Omite este campo cuando requires_postproduction es true."
                ),
            },
        },
        "required": ["requires_postproduction", "ai_rationale"],
    },
)

_GENERATE_CONFIG = types.GenerateContentConfig(
    tools=[types.Tool(function_declarations=[_EVALUATE_DECLARATION])],
    tool_config=types.ToolConfig(
        function_calling_config=types.FunctionCallingConfig(
            mode="ANY",
            allowed_function_names=["evaluate_postproduction_request"],
        )
    ),
)

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_TEXT_ONLY_PROMPT = """\
Eres el Ingestor Analítico de FrameFlow, una herramienta de postproducción cinematográfica.

Primero decide si la nota requiere trabajo real de postproducción (VFX, color, sonido o edición).
Notas de logística, catering, transporte, horarios, felicitaciones, conversaciones no relacionadas
o cualquier pedido que no implique trabajo de VFX, color, sonido ni edición NO requieren postproducción.

Si la nota SÍ requiere postproducción:
  - Clasifícala en exactamente un departamento: vfx, color, sound o editorial.
  - Asigna prioridad: low, medium, high o critical.
  - Explica el motivo concreto en español.

Si la nota NO requiere postproducción:
  - Indica la razón específica (ej. logística, catering, horarios, etc.).
  - No inventes trabajo de postproducción donde no lo hay.

Toma: {shot_id}
Nota del director: {director_note}
"""

_VIDEO_PROMPT = """\
Eres el Ingestor Analítico de FrameFlow, una herramienta de postproducción cinematográfica.
Se te proporciona una nota de dirección y un video de referencia de la toma.

Primero decide si la nota (y/o el video) requiere trabajo real de postproducción (VFX, color,
sonido o edición). Notas de logística, catering, transporte, horarios, felicitaciones,
conversaciones no relacionadas o cualquier pedido que no implique trabajo de VFX, color,
sonido ni edición NO requieren postproducción.

Si SÍ requiere postproducción:
  - Clasifícala en exactamente un departamento: vfx, color, sound o editorial.
  - Asigna prioridad: low, medium, high o critical.
  - En ai_rationale, indica si la decisión se basa en la NOTA, el VIDEO o en AMBOS,
    y qué elemento concreto de cada fuente influyó en la decisión.

Si NO requiere postproducción:
  - Indica la razón específica.
  - No inventes trabajo de postproducción.

Toma: {shot_id}
Nota del director: {director_note}
"""

_MULTIMODAL_PROMPT = """\
Eres el Ingestor Analítico de FrameFlow, una herramienta de postproducción cinematográfica.
Se te proporciona una nota de dirección y el fotograma correspondiente a esa toma.

Primero decide si la nota (y/o el fotograma) requiere trabajo real de postproducción (VFX, color,
sonido o edición). Notas de logística, catering, transporte, horarios, felicitaciones, conversaciones
no relacionadas o cualquier pedido que no implique trabajo de VFX, color, sonido ni edición
NO requieren postproducción.

Si SÍ requiere postproducción:
  - Clasifícala en exactamente un departamento: vfx, color, sound o editorial.
  - Asigna prioridad: low, medium, high o critical.
  - En ai_rationale, indica si la decisión se basa en la NOTA, el FOTOGRAMA o en AMBOS.

Si NO requiere postproducción:
  - Indica la razón específica.
  - No inventes trabajo de postproducción.

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
    # Internal helpers
    # ------------------------------------------------------------------

    def _extract_decision(
        self, response: types.GenerateContentResponse
    ) -> GeminiDecision:
        """Pull the function-call args out of a Gemini response."""
        function_call = next(
            (
                part.function_call
                for part in response.candidates[0].content.parts
                if part.function_call is not None
                and part.function_call.name == "evaluate_postproduction_request"
            ),
            None,
        )
        if function_call is None:
            raise RuntimeError("Gemini no devolvió la llamada de función esperada.")
        return GeminiDecision.model_validate(function_call.args)

    def _decision_to_result(
        self, decision: GeminiDecision, shot_id: str, director_note: str
    ) -> TicketCreate | EligibilityRejection:
        """Convert a GeminiDecision into either a TicketCreate or EligibilityRejection."""
        if not decision.requires_postproduction:
            return EligibilityRejection(
                requires_postproduction=False,
                ai_rationale=decision.ai_rationale,
                rejection_reason=decision.rejection_reason,
            )

        # requires_postproduction=True: department and priority must be present.
        if decision.department is None or decision.priority is None:
            raise RuntimeError(
                "Gemini indicó requires_postproduction=True pero omitió department o priority."
            )

        return TicketCreate(
            shot_id=shot_id,
            director_note=director_note,
            department=decision.department,
            priority=decision.priority,
            ai_rationale=decision.ai_rationale,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def classify(
        self, shot_id: str, director_note: str
    ) -> TicketCreate | EligibilityRejection:
        """Text-only eligibility check + classification."""
        client = self._create_client()
        prompt = _TEXT_ONLY_PROMPT.format(
            shot_id=shot_id, director_note=director_note
        ).strip()
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
            config=_GENERATE_CONFIG,
        )
        decision = self._extract_decision(response)
        return self._decision_to_result(decision, shot_id, director_note)

    def classify_with_image(
        self,
        shot_id: str,
        director_note: str,
        image_bytes: bytes,
        mime_type: str,
    ) -> TicketCreate | EligibilityRejection:
        """Multimodal eligibility check + classification: note + raw image bytes.

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
        decision = self._extract_decision(response)
        return self._decision_to_result(decision, shot_id, director_note)

    def classify_with_video(
        self,
        shot_id: str,
        director_note: str,
        gs_uri: str,
        mime_type: str,
    ) -> TicketCreate | EligibilityRejection:
        """Multimodal eligibility check + classification: note + GCS video URI.

        The video is referenced by its ``gs://`` URI and is NOT read into memory
        by the backend; Gemini fetches it directly from Cloud Storage.
        ``mime_type`` must be one of the values in ALLOWED_VIDEO_MIME_TYPES.
        """
        client = self._create_client()
        text_prompt = _VIDEO_PROMPT.format(
            shot_id=shot_id, director_note=director_note
        ).strip()
        contents = [
            types.Part.from_uri(file_uri=gs_uri, mime_type=mime_type),
            types.Part.from_text(text=text_prompt),
        ]
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=contents,
            config=_GENERATE_CONFIG,
        )
        decision = self._extract_decision(response)
        return self._decision_to_result(decision, shot_id, director_note)


gemini_classifier = GeminiClassifier()
