"""Tests for the multimodal ingestion endpoint.

All Gemini calls are mocked so no real API credentials are needed.
The tests validate:
  1. Text-only submission — text classify() is called, ticket is created.
  2. Valid image submission — classify_with_image() is called with correct args.
  3. Disallowed MIME type — 415 Unsupported Media Type.
  4. File too large — 413 Request Entity Too Large.
"""

from __future__ import annotations

import io
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app as fastapi_app
from app.models.ticket import Department, Priority, TicketCreate, TicketStatus

# ---------------------------------------------------------------------------
# Shared fixture — isolated in-memory database wired into the FastAPI app
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolated_db():
    """Override the get_db dependency with a fresh in-memory SQLite DB.

    SQLite ':memory:' opens a new database for each connection, so we pin
    all sessions to a single shared connection via
    ``connect_args={"uri": True}`` + ``file::memory:?cache=shared`` (or
    via StaticPool).  Using StaticPool is simpler and avoids URI quirks.
    """
    from sqlalchemy.pool import StaticPool

    import app.models.ticket_record  # noqa: F401  — register ORM model

    _engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=_engine)
    _Session = sessionmaker(bind=_engine, autocommit=False, autoflush=False)

    def override_get_db():
        db = _Session()
        try:
            yield db
        finally:
            db.close()

    fastapi_app.dependency_overrides[get_db] = override_get_db
    yield
    fastapi_app.dependency_overrides.clear()
    _engine.dispose()


@pytest.fixture()
def client():
    return TestClient(fastapi_app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MOCK_TICKET_CREATE = TicketCreate(
    shot_id="SC01-SH001",
    director_note="Remove the mic.",
    department=Department.VFX,
    priority=Priority.HIGH,
    ai_rationale="Microphone is visible in the frame.",
)

# Minimal 1×1 valid PNG (67 bytes)
_TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
    b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)

# Minimal valid JPEG header bytes (not a real image, but passes the MIME check)
_TINY_JPEG = bytes([0xFF, 0xD8, 0xFF, 0xE0] + [0x00] * 20)

# Tiny valid WebP RIFF header stub
_TINY_WEBP = b"RIFF\x24\x00\x00\x00WEBPVP8 \x18\x00\x00\x00" + b"\x00" * 20


# ---------------------------------------------------------------------------
# Test: text-only ingestion
# ---------------------------------------------------------------------------


class TestTextOnlyIngestion:
    def test_text_only_calls_classify_and_returns_ticket(self, client: TestClient):
        """POST without a frame calls classify() and returns a 201 ticket."""
        with patch(
            "app.api.ingestion.gemini_classifier.classify",
            return_value=_MOCK_TICKET_CREATE,
        ) as mock_classify:
            response = client.post(
                "/api/v1/ingestion/director-notes",
                data={"shot_id": "SC01-SH001", "director_note": "Remove the mic."},
            )

        assert response.status_code == 201
        body = response.json()
        assert body["shot_id"] == "SC01-SH001"
        assert body["status"] == TicketStatus.PENDING_REVIEW
        assert body["department"] == "vfx"
        mock_classify.assert_called_once_with("SC01-SH001", "Remove the mic.")

    def test_text_only_does_not_call_classify_with_image(self, client: TestClient):
        """When no frame is sent, classify_with_image must NOT be called."""
        with (
            patch("app.api.ingestion.gemini_classifier.classify", return_value=_MOCK_TICKET_CREATE),
            patch("app.api.ingestion.gemini_classifier.classify_with_image") as mock_multi,
        ):
            response = client.post(
                "/api/v1/ingestion/director-notes",
                data={"shot_id": "SC01-SH001", "director_note": "Remove the mic."},
            )

        assert response.status_code == 201
        mock_multi.assert_not_called()


# ---------------------------------------------------------------------------
# Test: multimodal ingestion — valid image
# ---------------------------------------------------------------------------


class TestMultimodalIngestion:
    def test_valid_png_calls_classify_with_image(self, client: TestClient):
        """POST with a valid PNG frame calls classify_with_image and returns 201."""
        with patch(
            "app.api.ingestion.gemini_classifier.classify_with_image",
            return_value=_MOCK_TICKET_CREATE,
        ) as mock_multi:
            response = client.post(
                "/api/v1/ingestion/director-notes",
                data={"shot_id": "SC01-SH001", "director_note": "Remove the mic."},
                files={"frame": ("frame.png", io.BytesIO(_TINY_PNG), "image/png")},
            )

        assert response.status_code == 201
        body = response.json()
        assert body["shot_id"] == "SC01-SH001"
        mock_multi.assert_called_once()
        call_args = mock_multi.call_args
        assert call_args.args[0] == "SC01-SH001"
        assert call_args.args[1] == "Remove the mic."
        assert call_args.args[2] == _TINY_PNG
        assert call_args.args[3] == "image/png"

    def test_valid_jpeg_is_accepted(self, client: TestClient):
        """JPEG content type is accepted and classify_with_image is invoked."""
        with patch(
            "app.api.ingestion.gemini_classifier.classify_with_image",
            return_value=_MOCK_TICKET_CREATE,
        ):
            response = client.post(
                "/api/v1/ingestion/director-notes",
                data={"shot_id": "SC02-SH002", "director_note": "Fix colour."},
                files={"frame": ("frame.jpg", io.BytesIO(_TINY_JPEG), "image/jpeg")},
            )
        assert response.status_code == 201

    def test_valid_webp_is_accepted(self, client: TestClient):
        """WebP content type is accepted."""
        with patch(
            "app.api.ingestion.gemini_classifier.classify_with_image",
            return_value=_MOCK_TICKET_CREATE,
        ):
            response = client.post(
                "/api/v1/ingestion/director-notes",
                data={"shot_id": "SC03-SH003", "director_note": "Colour grade."},
                files={"frame": ("frame.webp", io.BytesIO(_TINY_WEBP), "image/webp")},
            )
        assert response.status_code == 201

    def test_multimodal_ticket_is_persisted(self, client: TestClient):
        """Ticket from multimodal call is saved and visible in the tickets list."""
        with patch(
            "app.api.ingestion.gemini_classifier.classify_with_image",
            return_value=_MOCK_TICKET_CREATE,
        ):
            create_resp = client.post(
                "/api/v1/ingestion/director-notes",
                data={"shot_id": "SC01-SH001", "director_note": "Remove the mic."},
                files={"frame": ("frame.png", io.BytesIO(_TINY_PNG), "image/png")},
            )
        assert create_resp.status_code == 201
        ticket_id = create_resp.json()["id"]

        list_resp = client.get("/api/v1/tickets")
        assert list_resp.status_code == 200
        ids = [t["id"] for t in list_resp.json()]
        assert ticket_id in ids


# ---------------------------------------------------------------------------
# Test: disallowed MIME type → 415
# ---------------------------------------------------------------------------


class TestDisallowedMimeType:
    @pytest.mark.parametrize(
        "mime_type, filename",
        [
            ("image/gif", "anim.gif"),
            ("video/mp4", "clip.mp4"),
            ("application/pdf", "doc.pdf"),
            ("image/bmp", "bitmap.bmp"),
            ("text/plain", "note.txt"),
        ],
    )
    def test_disallowed_type_returns_415(self, client: TestClient, mime_type: str, filename: str):
        response = client.post(
            "/api/v1/ingestion/director-notes",
            data={"shot_id": "SC01-SH001", "director_note": "Test."},
            files={"frame": (filename, io.BytesIO(b"fake"), mime_type)},
        )
        assert response.status_code == 415
        assert "not allowed" in response.json()["detail"].lower()

    def test_disallowed_type_does_not_call_gemini(self, client: TestClient):
        with (
            patch("app.api.ingestion.gemini_classifier.classify") as mock_text,
            patch("app.api.ingestion.gemini_classifier.classify_with_image") as mock_multi,
        ):
            client.post(
                "/api/v1/ingestion/director-notes",
                data={"shot_id": "SC01-SH001", "director_note": "Test."},
                files={"frame": ("clip.mp4", io.BytesIO(b"fake"), "video/mp4")},
            )
        mock_text.assert_not_called()
        mock_multi.assert_not_called()


# ---------------------------------------------------------------------------
# Test: file too large → 413
# ---------------------------------------------------------------------------


class TestFileTooLarge:
    def test_oversized_file_returns_413(self, client: TestClient):
        oversized = b"x" * (10 * 1024 * 1024 + 1)  # 10 MiB + 1 byte
        response = client.post(
            "/api/v1/ingestion/director-notes",
            data={"shot_id": "SC01-SH001", "director_note": "Test."},
            files={"frame": ("big.png", io.BytesIO(oversized), "image/png")},
        )
        assert response.status_code == 413
        assert "10" in response.json()["detail"]

    def test_oversized_file_does_not_call_gemini(self, client: TestClient):
        oversized = b"x" * (10 * 1024 * 1024 + 1)
        with (
            patch("app.api.ingestion.gemini_classifier.classify") as mock_text,
            patch("app.api.ingestion.gemini_classifier.classify_with_image") as mock_multi,
        ):
            client.post(
                "/api/v1/ingestion/director-notes",
                data={"shot_id": "SC01-SH001", "director_note": "Test."},
                files={"frame": ("big.png", io.BytesIO(oversized), "image/png")},
            )
        mock_text.assert_not_called()
        mock_multi.assert_not_called()

    def test_exactly_at_limit_is_accepted(self, client: TestClient):
        """A file of exactly MAX_IMAGE_SIZE_BYTES must NOT trigger the 413."""
        exact_size = b"x" * (10 * 1024 * 1024)
        with patch(
            "app.api.ingestion.gemini_classifier.classify_with_image",
            return_value=_MOCK_TICKET_CREATE,
        ):
            response = client.post(
                "/api/v1/ingestion/director-notes",
                data={"shot_id": "SC01-SH001", "director_note": "Test."},
                files={"frame": ("exact.png", io.BytesIO(exact_size), "image/png")},
            )
        assert response.status_code == 201


# ---------------------------------------------------------------------------
# Test: dual-contract compatibility
# ---------------------------------------------------------------------------


class TestDualContractCompatibility:
    """Verify both application/json and multipart/form-data are accepted on
    the same endpoint, and that unsupported Content-Types are rejected."""

    # ------ JSON path -------------------------------------------------------

    def test_json_text_only_returns_201(self, client: TestClient):
        """Original JSON contract must still return 201 and a valid ticket."""
        with patch(
            "app.api.ingestion.gemini_classifier.classify",
            return_value=_MOCK_TICKET_CREATE,
        ) as mock_classify:
            response = client.post(
                "/api/v1/ingestion/director-notes",
                json={"shot_id": "SC01-SH001", "director_note": "Remove the mic."},
            )

        assert response.status_code == 201
        body = response.json()
        assert body["shot_id"] == "SC01-SH001"
        assert body["status"] == TicketStatus.PENDING_REVIEW
        mock_classify.assert_called_once_with("SC01-SH001", "Remove the mic.")

    def test_json_does_not_call_classify_with_image(self, client: TestClient):
        """JSON requests must never trigger the multimodal path."""
        with (
            patch("app.api.ingestion.gemini_classifier.classify", return_value=_MOCK_TICKET_CREATE),
            patch("app.api.ingestion.gemini_classifier.classify_with_image") as mock_multi,
        ):
            response = client.post(
                "/api/v1/ingestion/director-notes",
                json={"shot_id": "SC01-SH001", "director_note": "Remove the mic."},
            )

        assert response.status_code == 201
        mock_multi.assert_not_called()

    def test_json_missing_shot_id_returns_422(self, client: TestClient):
        """JSON body missing a required field must return 422."""
        response = client.post(
            "/api/v1/ingestion/director-notes",
            json={"director_note": "Remove the mic."},
        )
        assert response.status_code == 422

    def test_json_missing_director_note_returns_422(self, client: TestClient):
        """JSON body missing director_note must return 422."""
        response = client.post(
            "/api/v1/ingestion/director-notes",
            json={"shot_id": "SC01-SH001"},
        )
        assert response.status_code == 422

    def test_json_ticket_is_persisted(self, client: TestClient):
        """Ticket created via JSON is visible in the tickets list."""
        with patch(
            "app.api.ingestion.gemini_classifier.classify",
            return_value=_MOCK_TICKET_CREATE,
        ):
            resp = client.post(
                "/api/v1/ingestion/director-notes",
                json={"shot_id": "SC01-SH001", "director_note": "Remove the mic."},
            )
        assert resp.status_code == 201
        ticket_id = resp.json()["id"]

        list_resp = client.get("/api/v1/tickets")
        assert ticket_id in [t["id"] for t in list_resp.json()]

    # ------ multipart text-only path ----------------------------------------

    def test_multipart_text_only_calls_classify(self, client: TestClient):
        """multipart/form-data without a frame must call text-only classify()."""
        with patch(
            "app.api.ingestion.gemini_classifier.classify",
            return_value=_MOCK_TICKET_CREATE,
        ) as mock_classify:
            response = client.post(
                "/api/v1/ingestion/director-notes",
                data={"shot_id": "SC01-SH001", "director_note": "Remove the mic."},
            )

        assert response.status_code == 201
        mock_classify.assert_called_once_with("SC01-SH001", "Remove the mic.")

    def test_multipart_text_only_does_not_call_classify_with_image(self, client: TestClient):
        """multipart without frame must NOT call classify_with_image."""
        with (
            patch("app.api.ingestion.gemini_classifier.classify", return_value=_MOCK_TICKET_CREATE),
            patch("app.api.ingestion.gemini_classifier.classify_with_image") as mock_multi,
        ):
            response = client.post(
                "/api/v1/ingestion/director-notes",
                data={"shot_id": "SC01-SH001", "director_note": "Remove the mic."},
            )

        assert response.status_code == 201
        mock_multi.assert_not_called()

    # ------ multipart with image path ---------------------------------------

    def test_multipart_with_image_calls_classify_with_image(self, client: TestClient):
        """multipart/form-data with a valid PNG frame must call classify_with_image."""
        with patch(
            "app.api.ingestion.gemini_classifier.classify_with_image",
            return_value=_MOCK_TICKET_CREATE,
        ) as mock_multi:
            response = client.post(
                "/api/v1/ingestion/director-notes",
                data={"shot_id": "SC01-SH001", "director_note": "Remove the mic."},
                files={"frame": ("frame.png", io.BytesIO(_TINY_PNG), "image/png")},
            )

        assert response.status_code == 201
        mock_multi.assert_called_once()
        args = mock_multi.call_args.args
        assert args[0] == "SC01-SH001"
        assert args[1] == "Remove the mic."
        assert args[2] == _TINY_PNG
        assert args[3] == "image/png"

    def test_multipart_with_image_does_not_call_text_classify(self, client: TestClient):
        """multipart with a frame must NOT call the text-only classify()."""
        with (
            patch("app.api.ingestion.gemini_classifier.classify") as mock_text,
            patch(
                "app.api.ingestion.gemini_classifier.classify_with_image",
                return_value=_MOCK_TICKET_CREATE,
            ),
        ):
            response = client.post(
                "/api/v1/ingestion/director-notes",
                data={"shot_id": "SC01-SH001", "director_note": "Remove the mic."},
                files={"frame": ("frame.png", io.BytesIO(_TINY_PNG), "image/png")},
            )

        assert response.status_code == 201
        mock_text.assert_not_called()

    # ------ unsupported Content-Type → 415 ----------------------------------

    def test_unsupported_content_type_returns_415(self, client: TestClient):
        """Sending a truly unsupported Content-Type must return 415."""
        response = client.post(
            "/api/v1/ingestion/director-notes",
            content=b"<root/>",
            headers={"Content-Type": "text/xml"},
        )
        assert response.status_code == 415
        assert "unsupported" in response.json()["detail"].lower()

    def test_unsupported_content_type_text_plain_returns_415(self, client: TestClient):
        """text/plain must be rejected with 415."""
        response = client.post(
            "/api/v1/ingestion/director-notes",
            content=b"some text",
            headers={"Content-Type": "text/plain"},
        )
        assert response.status_code == 415

    def test_unsupported_content_type_does_not_call_gemini(self, client: TestClient):
        """Gemini must not be called when Content-Type is unsupported."""
        with (
            patch("app.api.ingestion.gemini_classifier.classify") as mock_text,
            patch("app.api.ingestion.gemini_classifier.classify_with_image") as mock_multi,
        ):
            client.post(
                "/api/v1/ingestion/director-notes",
                content=b"<root/>",
                headers={"Content-Type": "text/xml"},
            )
        mock_text.assert_not_called()
        mock_multi.assert_not_called()

    def test_url_encoded_text_only_is_accepted(self, client: TestClient):
        """application/x-www-form-urlencoded (text fields only) must return 201."""
        with patch(
            "app.api.ingestion.gemini_classifier.classify",
            return_value=_MOCK_TICKET_CREATE,
        ) as mock_classify:
            response = client.post(
                "/api/v1/ingestion/director-notes",
                content=b"shot_id=SC01-SH001&director_note=Remove+the+mic.",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        assert response.status_code == 201
        mock_classify.assert_called_once()

    # ------ both contracts produce the same response shape ------------------

    def test_json_and_multipart_return_same_ticket_shape(self, client: TestClient):
        """Tickets created via JSON and multipart must have identical schemas."""
        with patch(
            "app.api.ingestion.gemini_classifier.classify",
            return_value=_MOCK_TICKET_CREATE,
        ):
            json_resp = client.post(
                "/api/v1/ingestion/director-notes",
                json={"shot_id": "SC01-SH001", "director_note": "Remove the mic."},
            )
            form_resp = client.post(
                "/api/v1/ingestion/director-notes",
                data={"shot_id": "SC01-SH001", "director_note": "Remove the mic."},
            )

        expected_keys = {
            "id", "shot_id", "director_note", "department",
            "priority", "status", "ai_rationale", "supervisor_note",
            "artist_note", "supervisor_feedback",
            "production_id",
            "assigned_to_uid", "assigned_to_name",
            "created_at", "updated_at",
        }
        assert json_resp.status_code == 201
        assert form_resp.status_code == 201
        assert set(json_resp.json().keys()) == expected_keys
        assert set(form_resp.json().keys()) == expected_keys
