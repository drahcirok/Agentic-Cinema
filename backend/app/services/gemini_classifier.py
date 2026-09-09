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
        "Determine whether a director's note requires actual post-production work. "
        "If it does, classify the department and priority. "
        "If it does not, explain why it is not applicable."
    ),
    parameters={
        "type": "object",
        "properties": {
            "requires_postproduction": {
                "type": "boolean",
                "description": (
                    "true when the note requires actual VFX, color, sound, or editorial work. "
                    "false for notes about logistics, catering, transportation, scheduling, "
                    "congratulations, unrelated conversations, or any request that does not "
                    "involve actual post-production work."
                ),
            },
            "department": {
                "type": "string",
                "enum": ["vfx", "color", "sound", "editorial"],
                "description": (
                    "Primary responsible department. "
                    "Required when requires_postproduction is true. "
                    "Omit this field when requires_postproduction is false."
                ),
            },
            "priority": {
                "type": "string",
                "enum": ["low", "medium", "high", "critical"],
                "description": (
                    "Priority based on delivery impact. "
                    "Required when requires_postproduction is true. "
                    "Omit this field when requires_postproduction is false."
                ),
            },
            "ai_rationale": {
                "type": "string",
                "description": (
                    "Brief, specific explanation in natural English, regardless of the "
                    "language of the director's note. Explicitly state whether the decision "
                    "is based on the NOTE, the FRAME, the VIDEO, or a combination of them."
                ),
            },
            "rejection_reason": {
                "type": "string",
                "description": (
                    "Rejection category in natural English when requires_postproduction is false. "
                    "Examples: 'logistics', 'catering', 'transportation', 'scheduling', "
                    "'congratulations', 'matter unrelated to post-production'. "
                    "Omit this field when requires_postproduction is true."
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
You are FrameFlow's Analytical Intake Assistant for film post-production.

First, decide whether the note requires actual post-production work (VFX, color, sound, or editorial).
Notes about logistics, catering, transportation, scheduling, congratulations, unrelated conversations,
or any request that does not involve VFX, color, sound, or editorial work DO NOT require post-production.

If the note DOES require post-production:
  - Classify it into exactly one department: vfx, color, sound, or editorial.
  - Assign a priority: low, medium, high, or critical.
  - Explain the specific reason in natural English.

If the note DOES NOT require post-production:
  - Give the specific reason in natural English (for example, logistics, catering, or scheduling).
  - Do not invent post-production work where none is requested.

Always write ai_rationale and rejection_reason in English, regardless of the language of the note.

Shot: {shot_id}
Director's note: {director_note}
"""

_VIDEO_PROMPT = """\
You are FrameFlow's Analytical Intake Assistant for film post-production.
You are given a director's note and a reference video for the shot.

First, decide whether the note, the video, or both require actual post-production work (VFX, color,
sound, or editorial). Notes about logistics, catering, transportation, scheduling, congratulations,
unrelated conversations, or any request that does not involve VFX, color, sound, or editorial work
DO NOT require post-production.

If post-production IS required:
  - Classify it into exactly one department: vfx, color, sound, or editorial.
  - Assign a priority: low, medium, high, or critical.
  - In ai_rationale, state whether the decision is based on the NOTE, the VIDEO, or BOTH,
    and identify the specific element from each source that influenced the decision.

If post-production IS NOT required:
  - Give the specific reason.
  - Do not invent post-production work.

Always write ai_rationale and rejection_reason in English, regardless of the language of the note.

Shot: {shot_id}
Director's note: {director_note}
"""

_MULTIMODAL_PROMPT = """\
You are FrameFlow's Analytical Intake Assistant for film post-production.
You are given a director's note and the corresponding frame from that shot.

First, decide whether the note, the frame, or both require actual post-production work (VFX, color,
sound, or editorial). Notes about logistics, catering, transportation, scheduling, congratulations,
unrelated conversations, or any request that does not involve VFX, color, sound, or editorial work
DO NOT require post-production.

If post-production IS required:
  - Classify it into exactly one department: vfx, color, sound, or editorial.
  - Assign a priority: low, medium, high, or critical.
  - In ai_rationale, state whether the decision is based on the NOTE, the FRAME, or BOTH.

If post-production IS NOT required:
  - Give the specific reason.
  - Do not invent post-production work.

Always write ai_rationale and rejection_reason in English, regardless of the language of the note.

Shot: {shot_id}
Director's note: {director_note}
"""


class GeminiConfigurationError(Exception):
    """Gemini cannot run because required configuration is missing."""


class GeminiClassifier:
    def _create_client(self) -> genai.Client:
        """
        Create the Gemini client according to GEMINI_BACKEND:

        - "vertex_ai": automatically uses Application Default Credentials (ADC).
          Requires GOOGLE_CLOUD_PROJECT and GOOGLE_CLOUD_LOCATION=global.

        - "developer": uses GEMINI_API_KEY for local development.
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
                "GEMINI_BACKEND=developer requires GEMINI_API_KEY."
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
            raise RuntimeError("Gemini did not return the expected function call.")
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
                "Gemini returned requires_postproduction=True but omitted department or priority."
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
