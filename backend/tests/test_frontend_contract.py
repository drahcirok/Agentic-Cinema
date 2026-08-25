"""Frontend-contract tests for the ingestion endpoint.

These tests verify that the HTTP 200 response produced by the backend
contains exactly the fields the frontend component reads:
  - requires_postproduction  (boolean, must be false)
  - ai_rationale             (string, must be non-empty)
  - rejection_reason         (string | null)

They also confirm that the HTTP 201 response contains the fields the
frontend reads when adding a card to the Kanban:
  - id, shot_id, director_note, department, priority, status

All Gemini calls are mocked.
"""

from __future__ import annotations

import io
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app as fastapi_app
from app.models.ingestion import EligibilityRejection
from app.models.ticket import Department, Priority, TicketCreate, TicketStatus


# ---------------------------------------------------------------------------
# Fixtures (same pattern used across the test suite)
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolated_db():
    import app.models.ticket_record  # noqa: F401

    _engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=_engine)
    _Session = sessionmaker(bind=_engine, autocommit=False, autoflush=False)

    def _override():
        db = _Session()
        try:
            yield db
        finally:
            db.close()

    fastapi_app.dependency_overrides[get_db] = _override
    yield
    fastapi_app.dependency_overrides.clear()
    _engine.dispose()


@pytest.fixture()
def client():
    return TestClient(fastapi_app)


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------

_TICKET_CREATE = TicketCreate(
    shot_id="SC01-SH001",
    director_note="Remove the boom mic.",
    department=Department.VFX,
    priority=Priority.HIGH,
    ai_rationale="Microphone visible in the top-left corner.",
)

_REJECTION_WITH_REASON = EligibilityRejection(
    requires_postproduction=False,
    ai_rationale="La nota describe un problema de logística, no de postproducción.",
    rejection_reason="logística",
)

_REJECTION_NO_REASON = EligibilityRejection(
    requires_postproduction=False,
    ai_rationale="Felicitación sin trabajo de postproducción.",
    rejection_reason=None,
)

_TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
    b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)


# ---------------------------------------------------------------------------
# 200 response — fields the frontend reads for the "info" variant message
# ---------------------------------------------------------------------------


class TestFrontendContractHttp200:
    """Verify every field the DirectorNoteForm component reads from a 200 body."""

    def test_200_has_requires_postproduction_false(self, client: TestClient):
        with patch("app.api.ingestion.gemini_classifier.classify", return_value=_REJECTION_WITH_REASON):
            resp = client.post(
                "/api/v1/ingestion/director-notes",
                json={"shot_id": "SC01-SH001", "director_note": "El catering llegó tarde."},
            )
        assert resp.status_code == 200
        assert resp.json()["requires_postproduction"] is False

    def test_200_has_non_empty_ai_rationale(self, client: TestClient):
        with patch("app.api.ingestion.gemini_classifier.classify", return_value=_REJECTION_WITH_REASON):
            resp = client.post(
                "/api/v1/ingestion/director-notes",
                json={"shot_id": "SC01-SH001", "director_note": "El catering llegó tarde."},
            )
        body = resp.json()
        assert "ai_rationale" in body
        assert isinstance(body["ai_rationale"], str)
        assert len(body["ai_rationale"]) > 0

    def test_200_rejection_reason_is_string_when_present(self, client: TestClient):
        with patch("app.api.ingestion.gemini_classifier.classify", return_value=_REJECTION_WITH_REASON):
            resp = client.post(
                "/api/v1/ingestion/director-notes",
                json={"shot_id": "SC01-SH001", "director_note": "El catering llegó tarde."},
            )
        body = resp.json()
        assert "rejection_reason" in body
        assert isinstance(body["rejection_reason"], str)

    def test_200_rejection_reason_is_null_when_absent(self, client: TestClient):
        """Frontend must handle rejection_reason=null without crashing."""
        with patch("app.api.ingestion.gemini_classifier.classify", return_value=_REJECTION_NO_REASON):
            resp = client.post(
                "/api/v1/ingestion/director-notes",
                json={"shot_id": "SC01-SH001", "director_note": "Buen trabajo a todos."},
            )
        assert resp.status_code == 200
        assert resp.json()["rejection_reason"] is None

    def test_200_does_not_contain_ticket_fields(self, client: TestClient):
        """Fields read from a 201 body must NOT appear in a 200 body, so the
        frontend cannot accidentally call onCreated() with an invalid object."""
        with patch("app.api.ingestion.gemini_classifier.classify", return_value=_REJECTION_WITH_REASON):
            resp = client.post(
                "/api/v1/ingestion/director-notes",
                json={"shot_id": "SC01-SH001", "director_note": "El catering llegó tarde."},
            )
        body = resp.json()
        for ticket_field in ("id", "department", "priority", "status", "created_at", "updated_at"):
            assert ticket_field not in body, (
                f"Field '{ticket_field}' must not appear in a 200 rejection response"
            )

    def test_200_message_text_can_be_built_from_rejection_reason(self, client: TestClient):
        """Simulate the frontend's message-text construction:
        f'No se creó ticket: esta nota no requiere postproducción. {rejection_reason}'
        The result must be a non-empty string."""
        with patch("app.api.ingestion.gemini_classifier.classify", return_value=_REJECTION_WITH_REASON):
            resp = client.post(
                "/api/v1/ingestion/director-notes",
                json={"shot_id": "SC01-SH001", "director_note": "El catering llegó tarde."},
            )
        body = resp.json()
        reason: str = body.get("rejection_reason") or body.get("ai_rationale") or ""
        text = f"No se creó ticket: esta nota no requiere postproducción.{' ' + reason if reason else ''}"
        assert text.startswith("No se creó ticket:")
        assert len(text) > len("No se creó ticket:")

    def test_200_via_multipart_has_same_shape(self, client: TestClient):
        """multipart/form-data path must produce the same 200 body as JSON."""
        with patch("app.api.ingestion.gemini_classifier.classify", return_value=_REJECTION_WITH_REASON):
            resp = client.post(
                "/api/v1/ingestion/director-notes",
                data={"shot_id": "SC01-SH001", "director_note": "El catering llegó tarde."},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["requires_postproduction"] is False
        assert "ai_rationale" in body
        assert "rejection_reason" in body

    def test_200_via_multipart_with_frame_has_same_shape(self, client: TestClient):
        """Even when a frame is attached, the 200 rejection body must have
        the fields the frontend expects."""
        with patch(
            "app.api.ingestion.gemini_classifier.classify_with_image",
            return_value=_REJECTION_WITH_REASON,
        ):
            resp = client.post(
                "/api/v1/ingestion/director-notes",
                data={"shot_id": "SC01-SH001", "director_note": "Buen trabajo equipo."},
                files={"frame": ("frame.png", io.BytesIO(_TINY_PNG), "image/png")},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["requires_postproduction"] is False
        assert "ai_rationale" in body


# ---------------------------------------------------------------------------
# 201 response — fields the frontend reads to build a Kanban card
# ---------------------------------------------------------------------------


class TestFrontendContractHttp201:
    """Verify every field the DirectorNoteForm component passes to onCreated()."""

    _REQUIRED_TICKET_FIELDS = {
        "id", "shot_id", "director_note", "department",
        "priority", "status", "ai_rationale", "supervisor_note",
        "created_at", "updated_at",
    }

    def test_201_contains_all_kanban_fields(self, client: TestClient):
        with patch("app.api.ingestion.gemini_classifier.classify", return_value=_TICKET_CREATE):
            resp = client.post(
                "/api/v1/ingestion/director-notes",
                json={"shot_id": "SC01-SH001", "director_note": "Remove the boom mic."},
            )
        assert resp.status_code == 201
        body = resp.json()
        assert self._REQUIRED_TICKET_FIELDS.issubset(body.keys())

    def test_201_status_is_pending_review(self, client: TestClient):
        with patch("app.api.ingestion.gemini_classifier.classify", return_value=_TICKET_CREATE):
            resp = client.post(
                "/api/v1/ingestion/director-notes",
                json={"shot_id": "SC01-SH001", "director_note": "Remove the boom mic."},
            )
        assert resp.json()["status"] == TicketStatus.PENDING_REVIEW

    def test_201_department_matches_classifier_output(self, client: TestClient):
        with patch("app.api.ingestion.gemini_classifier.classify", return_value=_TICKET_CREATE):
            resp = client.post(
                "/api/v1/ingestion/director-notes",
                json={"shot_id": "SC01-SH001", "director_note": "Remove the boom mic."},
            )
        assert resp.json()["department"] == "vfx"

    def test_201_id_is_uuid_string(self, client: TestClient):
        import uuid

        with patch("app.api.ingestion.gemini_classifier.classify", return_value=_TICKET_CREATE):
            resp = client.post(
                "/api/v1/ingestion/director-notes",
                json={"shot_id": "SC01-SH001", "director_note": "Remove the boom mic."},
            )
        ticket_id = resp.json()["id"]
        # Must not raise
        uuid.UUID(ticket_id)
