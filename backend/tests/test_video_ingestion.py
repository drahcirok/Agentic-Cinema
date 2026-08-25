"""Tests for the video ingestion path.

All Gemini calls and all GCS calls are mocked — no real credentials needed.

Scenarios covered
-----------------
1.  Valid MP4: upload → classify_with_video → cleanup → 201 + DB row.
2.  Cleanup when Gemini raises an exception (502, no DB row, delete called).
3.  Cleanup when Gemini returns EligibilityRejection (200, no DB row, delete called).
4.  Oversized video (> 50 MiB) → 413, upload never called.
5.  Empty video (0 bytes) → 422, upload never called.
6.  Wrong MIME type (video/avi) → 415, upload never called.
7.  frame + video together → 422, upload never called.
8.  Missing bucket (StorageConfigurationError) → 503, Gemini never called.
9.  GCS upload generic failure → 502.
10. Regression — JSON text-only path still works (201) with video path present.
11. Regression — multipart image (frame) path still works (201).
"""

from __future__ import annotations

import io
from unittest.mock import MagicMock, call, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app as fastapi_app
from app.models.ingestion import EligibilityRejection
from app.models.ticket import Department, Priority, TicketCreate, TicketStatus

# ---------------------------------------------------------------------------
# Shared fixture — isolated in-memory database wired into the FastAPI app
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolated_db():
    """Fresh StaticPool in-memory SQLite for every test."""
    import app.models.ticket_record  # noqa: F401  — register ORM model

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
    yield _engine
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
    ai_rationale="Mic visible in the footage.",
)

_MOCK_ELIGIBILITY_REJECTION = EligibilityRejection(
    requires_postproduction=False,
    ai_rationale="The note is about catering.",
    rejection_reason="catering",
)

# Minimal valid MP4 stub — just enough bytes to pass the size/empty checks.
# (Not a real parseable video, but MIME is validated by content-type header.)
_TINY_MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 24

_GS_URI = "gs://test-bucket/uploads/videos/some-uuid.mp4"


def _mp4_file(size_bytes: int = len(_TINY_MP4)) -> io.BytesIO:
    """Return a BytesIO of *size_bytes* with video/mp4 content."""
    data = _TINY_MP4 if size_bytes == len(_TINY_MP4) else (b"\x00" * size_bytes)
    buf = io.BytesIO(data)
    buf.name = "clip.mp4"
    return buf


# ---------------------------------------------------------------------------
# Test class: happy-path video ingestion
# ---------------------------------------------------------------------------


class TestVideoIngestionHappyPath:
    def test_valid_mp4_returns_201_and_creates_db_row(
        self, client: TestClient, _isolated_db
    ):
        """A valid MP4 upload goes through upload → Gemini → cleanup → 201."""
        with (
            patch(
                "app.api.ingestion.video_storage.upload_video",
                return_value=_GS_URI,
            ) as mock_upload,
            patch(
                "app.api.ingestion.video_storage.delete_object"
            ) as mock_delete,
            patch(
                "app.api.ingestion.gemini_classifier.classify_with_video",
                return_value=_MOCK_TICKET_CREATE,
            ) as mock_classify,
        ):
            response = client.post(
                "/api/v1/ingestion/director-notes",
                files={"video": ("clip.mp4", _mp4_file(), "video/mp4")},
                data={"shot_id": "SC01-SH001", "director_note": "Remove the mic."},
            )

        assert response.status_code == 201
        body = response.json()
        assert body["shot_id"] == "SC01-SH001"
        assert body["status"] == TicketStatus.PENDING_REVIEW

        # All three service calls must have happened.
        mock_upload.assert_called_once()
        mock_classify.assert_called_once_with(
            "SC01-SH001", "Remove the mic.", _GS_URI, "video/mp4"
        )
        mock_delete.assert_called_once_with(_GS_URI)

    def test_valid_mp4_ticket_is_persisted_in_db(
        self, client: TestClient, _isolated_db
    ):
        """The ticket row is readable from a new Session after the request."""
        with (
            patch(
                "app.api.ingestion.video_storage.upload_video",
                return_value=_GS_URI,
            ),
            patch("app.api.ingestion.video_storage.delete_object"),
            patch(
                "app.api.ingestion.gemini_classifier.classify_with_video",
                return_value=_MOCK_TICKET_CREATE,
            ),
        ):
            response = client.post(
                "/api/v1/ingestion/director-notes",
                files={"video": ("clip.mp4", _mp4_file(), "video/mp4")},
                data={"shot_id": "SC01-SH001", "director_note": "Remove the mic."},
            )

        assert response.status_code == 201
        ticket_id = response.json()["id"]

        # Open a brand-new session and verify the row is there.
        _Session = sessionmaker(bind=_isolated_db)
        with _Session() as db:
            from app.models.ticket_record import TicketRecord

            row = db.get(TicketRecord, ticket_id)
            assert row is not None
            assert row.shot_id == "SC01-SH001"
            assert row.status == TicketStatus.PENDING_REVIEW

    def test_classify_with_video_receives_correct_gs_uri(
        self, client: TestClient, _isolated_db
    ):
        """classify_with_video is called with the URI returned by upload_video."""
        custom_uri = "gs://my-bucket/uploads/videos/custom.mp4"
        with (
            patch(
                "app.api.ingestion.video_storage.upload_video",
                return_value=custom_uri,
            ),
            patch("app.api.ingestion.video_storage.delete_object"),
            patch(
                "app.api.ingestion.gemini_classifier.classify_with_video",
                return_value=_MOCK_TICKET_CREATE,
            ) as mock_classify,
        ):
            client.post(
                "/api/v1/ingestion/director-notes",
                files={"video": ("clip.mp4", _mp4_file(), "video/mp4")},
                data={"shot_id": "SC01-SH001", "director_note": "Remove the mic."},
            )

        mock_classify.assert_called_once_with(
            "SC01-SH001", "Remove the mic.", custom_uri, "video/mp4"
        )


# ---------------------------------------------------------------------------
# Test class: cleanup guarantees
# ---------------------------------------------------------------------------


class TestVideoCleanup:
    def test_gcs_object_deleted_when_gemini_raises(
        self, client: TestClient, _isolated_db
    ):
        """Even if Gemini throws, delete_object must still be called."""
        with (
            patch(
                "app.api.ingestion.video_storage.upload_video",
                return_value=_GS_URI,
            ),
            patch(
                "app.api.ingestion.video_storage.delete_object"
            ) as mock_delete,
            patch(
                "app.api.ingestion.gemini_classifier.classify_with_video",
                side_effect=RuntimeError("Gemini boom"),
            ),
        ):
            response = client.post(
                "/api/v1/ingestion/director-notes",
                files={"video": ("clip.mp4", _mp4_file(), "video/mp4")},
                data={"shot_id": "SC01-SH001", "director_note": "Remove the mic."},
            )

        assert response.status_code == 502
        mock_delete.assert_called_once_with(_GS_URI)

    def test_gcs_object_deleted_when_gemini_rejects_eligibility(
        self, client: TestClient, _isolated_db
    ):
        """When Gemini returns EligibilityRejection (200), cleanup still runs."""
        with (
            patch(
                "app.api.ingestion.video_storage.upload_video",
                return_value=_GS_URI,
            ),
            patch(
                "app.api.ingestion.video_storage.delete_object"
            ) as mock_delete,
            patch(
                "app.api.ingestion.gemini_classifier.classify_with_video",
                return_value=_MOCK_ELIGIBILITY_REJECTION,
            ),
        ):
            response = client.post(
                "/api/v1/ingestion/director-notes",
                files={"video": ("clip.mp4", _mp4_file(), "video/mp4")},
                data={"shot_id": "SC01-SH001", "director_note": "Not post-production."},
            )

        assert response.status_code == 200
        assert response.json()["requires_postproduction"] is False
        mock_delete.assert_called_once_with(_GS_URI)

    def test_no_db_row_when_gemini_rejects_eligibility(
        self, client: TestClient, _isolated_db
    ):
        """No SQLite row is written when requires_postproduction=False."""
        with (
            patch("app.api.ingestion.video_storage.upload_video", return_value=_GS_URI),
            patch("app.api.ingestion.video_storage.delete_object"),
            patch(
                "app.api.ingestion.gemini_classifier.classify_with_video",
                return_value=_MOCK_ELIGIBILITY_REJECTION,
            ),
        ):
            client.post(
                "/api/v1/ingestion/director-notes",
                files={"video": ("clip.mp4", _mp4_file(), "video/mp4")},
                data={"shot_id": "SC01-SH001", "director_note": "Not post-production."},
            )

        _Session = sessionmaker(bind=_isolated_db)
        with _Session() as db:
            from app.models.ticket_record import TicketRecord

            count = db.query(TicketRecord).count()
            assert count == 0


# ---------------------------------------------------------------------------
# Test class: cleanup failure resilience — a broken delete_object must never
# replace or hide the primary response (201/200) or the primary error (502).
# ---------------------------------------------------------------------------


class TestCleanupFailureResilience:
    """delete_object raising any exception must not affect the HTTP response."""

    def test_cleanup_failure_does_not_hide_201_response(
        self, client: TestClient, _isolated_db
    ):
        """Gemini succeeds → ticket created → cleanup throws → client still gets 201.

        This is the key regression: without the try/except guard in the finally
        block the exception from delete_object would propagate and turn the 201
        into a 500, silently discarding the created ticket from the response.
        """
        with (
            patch(
                "app.api.ingestion.video_storage.upload_video",
                return_value=_GS_URI,
            ),
            patch(
                "app.api.ingestion.video_storage.delete_object",
                side_effect=RuntimeError("GCS delete network error"),
            ),
            patch(
                "app.api.ingestion.gemini_classifier.classify_with_video",
                return_value=_MOCK_TICKET_CREATE,
            ),
        ):
            response = client.post(
                "/api/v1/ingestion/director-notes",
                files={"video": ("clip.mp4", _mp4_file(), "video/mp4")},
                data={"shot_id": "SC01-SH001", "director_note": "Remove the mic."},
            )

        assert response.status_code == 201, (
            "A cleanup failure must not replace the 201 ticket-created response."
        )
        body = response.json()
        assert body["shot_id"] == "SC01-SH001"
        assert body["status"] == TicketStatus.PENDING_REVIEW

    def test_cleanup_failure_does_not_hide_200_eligibility_rejection(
        self, client: TestClient, _isolated_db
    ):
        """Gemini rejects eligibility (200) → cleanup throws → client still gets 200.

        The EligibilityRejection response body must be preserved intact even
        when the subsequent best-effort GCS cleanup fails.
        """
        with (
            patch(
                "app.api.ingestion.video_storage.upload_video",
                return_value=_GS_URI,
            ),
            patch(
                "app.api.ingestion.video_storage.delete_object",
                side_effect=ConnectionError("GCS unreachable"),
            ),
            patch(
                "app.api.ingestion.gemini_classifier.classify_with_video",
                return_value=_MOCK_ELIGIBILITY_REJECTION,
            ),
        ):
            response = client.post(
                "/api/v1/ingestion/director-notes",
                files={"video": ("clip.mp4", _mp4_file(), "video/mp4")},
                data={"shot_id": "SC01-SH001", "director_note": "Not post-production."},
            )

        assert response.status_code == 200, (
            "A cleanup failure must not replace the 200 eligibility-rejection response."
        )
        body = response.json()
        assert body["requires_postproduction"] is False
        assert body["rejection_reason"] == "catering"

    def test_gemini_error_plus_cleanup_failure_preserves_502(
        self, client: TestClient, _isolated_db
    ):
        """Gemini raises (502) AND cleanup also raises → client still gets 502.

        The original Gemini error must not be replaced by the cleanup error.
        Without the guard, Python would replace the active exception with the
        one raised in the finally block, changing 502 → 500.
        """
        with (
            patch(
                "app.api.ingestion.video_storage.upload_video",
                return_value=_GS_URI,
            ),
            patch(
                "app.api.ingestion.video_storage.delete_object",
                side_effect=OSError("Permission denied on GCS delete"),
            ),
            patch(
                "app.api.ingestion.gemini_classifier.classify_with_video",
                side_effect=RuntimeError("Gemini crashed"),
            ),
        ):
            response = client.post(
                "/api/v1/ingestion/director-notes",
                files={"video": ("clip.mp4", _mp4_file(), "video/mp4")},
                data={"shot_id": "SC01-SH001", "director_note": "Remove the mic."},
            )

        assert response.status_code == 502, (
            "A cleanup failure must not replace the original Gemini 502 error."
        )
        assert "gemini" in response.json()["detail"].lower()

    def test_cleanup_failure_is_logged_not_raised(
        self, client: TestClient, _isolated_db, caplog
    ):
        """When cleanup fails, a WARNING is emitted — no credentials/tokens logged.

        The log message must contain the exception type but must NOT contain any
        value that could be a credential, token, or video content.
        """
        import logging

        with (
            patch(
                "app.api.ingestion.video_storage.upload_video",
                return_value=_GS_URI,
            ),
            patch(
                "app.api.ingestion.video_storage.delete_object",
                side_effect=TimeoutError("socket timeout"),
            ),
            patch(
                "app.api.ingestion.gemini_classifier.classify_with_video",
                return_value=_MOCK_TICKET_CREATE,
            ),
            caplog.at_level(logging.WARNING, logger="app.api.ingestion"),
        ):
            response = client.post(
                "/api/v1/ingestion/director-notes",
                files={"video": ("clip.mp4", _mp4_file(), "video/mp4")},
                data={"shot_id": "SC01-SH001", "director_note": "Remove the mic."},
            )

        # Primary response is still 201.
        assert response.status_code == 201

        # A warning was emitted.
        assert any(
            "TimeoutError" in msg or "cleanup" in msg.lower()
            for msg in caplog.messages
        ), "Expected a cleanup warning log entry."

        # The log must not contain the raw exception message ("socket timeout"
        # here, but in production this could be a GCS error with credentials).
        for msg in caplog.messages:
            assert "socket timeout" not in msg, (
                "Exception message must not appear in logs — "
                "it could contain sensitive data."
            )



# ---------------------------------------------------------------------------
# Test class: validation errors (upload_video must NOT be called)
# ---------------------------------------------------------------------------


class TestVideoValidationErrors:
    def test_oversized_video_returns_413(self, client: TestClient, _isolated_db):
        """A video larger than MAX_VIDEO_SIZE_BYTES is rejected before upload."""
        big_data = b"\x00" * (50 * 1024 * 1024 + 1)
        with patch(
            "app.api.ingestion.video_storage.upload_video"
        ) as mock_upload:
            response = client.post(
                "/api/v1/ingestion/director-notes",
                files={"video": ("big.mp4", io.BytesIO(big_data), "video/mp4")},
                data={"shot_id": "SC01-SH001", "director_note": "Big video."},
            )

        assert response.status_code == 413
        mock_upload.assert_not_called()

    def test_empty_video_returns_422(self, client: TestClient, _isolated_db):
        """An empty video file is rejected before upload."""
        with patch(
            "app.api.ingestion.video_storage.upload_video"
        ) as mock_upload:
            response = client.post(
                "/api/v1/ingestion/director-notes",
                files={"video": ("empty.mp4", io.BytesIO(b""), "video/mp4")},
                data={"shot_id": "SC01-SH001", "director_note": "Empty video."},
            )

        assert response.status_code == 422
        mock_upload.assert_not_called()

    def test_wrong_mime_type_returns_415(self, client: TestClient, _isolated_db):
        """A video with an unsupported MIME type is rejected before upload."""
        with patch(
            "app.api.ingestion.video_storage.upload_video"
        ) as mock_upload:
            response = client.post(
                "/api/v1/ingestion/director-notes",
                files={"video": ("clip.avi", _mp4_file(), "video/avi")},
                data={"shot_id": "SC01-SH001", "director_note": "AVI file."},
            )

        assert response.status_code == 415
        mock_upload.assert_not_called()

    def test_frame_and_video_together_returns_422(
        self, client: TestClient, _isolated_db
    ):
        """Sending both frame and video in the same request returns 422."""
        tiny_png = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
            b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        with patch(
            "app.api.ingestion.video_storage.upload_video"
        ) as mock_upload:
            response = client.post(
                "/api/v1/ingestion/director-notes",
                files={
                    "frame": ("frame.png", io.BytesIO(tiny_png), "image/png"),
                    "video": ("clip.mp4", _mp4_file(), "video/mp4"),
                },
                data={"shot_id": "SC01-SH001", "director_note": "Both media."},
            )

        assert response.status_code == 422
        assert "frame" in response.json()["detail"].lower() or "video" in response.json()["detail"].lower()
        mock_upload.assert_not_called()


# ---------------------------------------------------------------------------
# Test class: configuration errors
# ---------------------------------------------------------------------------


class TestVideoConfigurationErrors:
    def test_missing_bucket_returns_503(self, client: TestClient, _isolated_db):
        """When upload_video raises StorageConfigurationError, return 503."""
        from app.services.video_storage import StorageConfigurationError

        with (
            patch(
                "app.api.ingestion.video_storage.upload_video",
                side_effect=StorageConfigurationError("GOOGLE_CLOUD_STORAGE_BUCKET not set"),
            ),
            patch(
                "app.api.ingestion.gemini_classifier.classify_with_video"
            ) as mock_classify,
        ):
            response = client.post(
                "/api/v1/ingestion/director-notes",
                files={"video": ("clip.mp4", _mp4_file(), "video/mp4")},
                data={"shot_id": "SC01-SH001", "director_note": "Remove the mic."},
            )

        assert response.status_code == 503
        assert "storage" in response.json()["detail"].lower() or "bucket" in response.json()["detail"].lower()
        mock_classify.assert_not_called()

    def test_gcs_upload_generic_failure_returns_502(
        self, client: TestClient, _isolated_db
    ):
        """When upload_video raises a generic exception, return 502."""
        with (
            patch(
                "app.api.ingestion.video_storage.upload_video",
                side_effect=ConnectionError("Network error"),
            ),
            patch(
                "app.api.ingestion.gemini_classifier.classify_with_video"
            ) as mock_classify,
        ):
            response = client.post(
                "/api/v1/ingestion/director-notes",
                files={"video": ("clip.mp4", _mp4_file(), "video/mp4")},
                data={"shot_id": "SC01-SH001", "director_note": "Remove the mic."},
            )

        assert response.status_code == 502
        mock_classify.assert_not_called()


# ---------------------------------------------------------------------------
# Test class: regression — existing paths still work
# ---------------------------------------------------------------------------


class TestVideoRegressionExistingPaths:
    def test_json_text_only_still_returns_201(
        self, client: TestClient, _isolated_db
    ):
        """The JSON text-only path is unaffected by the video path."""
        with patch(
            "app.api.ingestion.gemini_classifier.classify",
            return_value=_MOCK_TICKET_CREATE,
        ):
            response = client.post(
                "/api/v1/ingestion/director-notes",
                json={"shot_id": "SC01-SH001", "director_note": "Remove the mic."},
            )

        assert response.status_code == 201
        assert response.json()["department"] == "vfx"

    def test_multipart_frame_path_still_returns_201(
        self, client: TestClient, _isolated_db
    ):
        """The multipart image (frame) path is unaffected by the video path."""
        tiny_png = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
            b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        with patch(
            "app.api.ingestion.gemini_classifier.classify_with_image",
            return_value=_MOCK_TICKET_CREATE,
        ):
            response = client.post(
                "/api/v1/ingestion/director-notes",
                files={"frame": ("frame.png", io.BytesIO(tiny_png), "image/png")},
                data={"shot_id": "SC01-SH001", "director_note": "Remove the mic."},
            )

        assert response.status_code == 201
        assert response.json()["department"] == "vfx"

    def test_video_path_does_not_call_text_classify(
        self, client: TestClient, _isolated_db
    ):
        """When a video is attached, only classify_with_video is called."""
        with (
            patch("app.api.ingestion.video_storage.upload_video", return_value=_GS_URI),
            patch("app.api.ingestion.video_storage.delete_object"),
            patch(
                "app.api.ingestion.gemini_classifier.classify_with_video",
                return_value=_MOCK_TICKET_CREATE,
            ) as mock_video_classify,
            patch(
                "app.api.ingestion.gemini_classifier.classify"
            ) as mock_text_classify,
            patch(
                "app.api.ingestion.gemini_classifier.classify_with_image"
            ) as mock_image_classify,
        ):
            client.post(
                "/api/v1/ingestion/director-notes",
                files={"video": ("clip.mp4", _mp4_file(), "video/mp4")},
                data={"shot_id": "SC01-SH001", "director_note": "Remove the mic."},
            )

        mock_video_classify.assert_called_once()
        mock_text_classify.assert_not_called()
        mock_image_classify.assert_not_called()
