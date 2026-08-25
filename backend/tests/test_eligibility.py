"""Eligibility gate tests for the ingestion endpoint.

Covers all scenarios required by the feature spec:
  1. VFX note creates a ticket.
  2. Sound note creates a ticket in the sound department.
  3. Colour note creates a ticket in the color department.
  4. Catering note does NOT create a ticket and leaves SQLite empty.
  5. Irrelevant note WITH a frame does NOT create a ticket.
  6. The 200-rejection response shape does not break the frontend contract.
  7. Compatibility across JSON, multipart and URL-encoded Content-Types.

All Gemini calls are mocked — no real credentials are needed.
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
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolated_db():
    """Fresh StaticPool in-memory SQLite for every test."""
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
    yield _engine  # yield the engine so tests can query SQLite directly
    fastapi_app.dependency_overrides.clear()
    _engine.dispose()


@pytest.fixture()
def client():
    return TestClient(fastapi_app)


# ---------------------------------------------------------------------------
# Mock return values
# ---------------------------------------------------------------------------

def _ticket_create(dept: Department, priority: Priority = Priority.HIGH) -> TicketCreate:
    return TicketCreate(
        shot_id="SC01-SH001",
        director_note="Test note.",
        department=dept,
        priority=priority,
        ai_rationale=f"Classified to {dept} based on the note.",
    )


_REJECTION = EligibilityRejection(
    requires_postproduction=False,
    ai_rationale="La nota se refiere a un aspecto de logística, no de postproducción.",
    rejection_reason="logística",
)

# Minimal 1×1 PNG used for multimodal tests
_TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
    b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)


# ---------------------------------------------------------------------------
# Helper — count rows in SQLite directly
# ---------------------------------------------------------------------------

def _ticket_count(engine) -> int:
    from sqlalchemy import text as sa_text
    with engine.connect() as conn:
        return conn.execute(sa_text("SELECT COUNT(*) FROM postproduction_tickets")).scalar()


# ---------------------------------------------------------------------------
# 1. VFX note creates a ticket
# ---------------------------------------------------------------------------

class TestVfxNoteCreatesTicket:
    def test_vfx_json_returns_201(self, client: TestClient, _isolated_db):
        with patch(
            "app.api.ingestion.gemini_classifier.classify",
            return_value=_ticket_create(Department.VFX),
        ):
            resp = client.post(
                "/api/v1/ingestion/director-notes",
                json={"shot_id": "SC01-SH001", "director_note": "Remove the boom mic."},
            )

        assert resp.status_code == 201
        body = resp.json()
        assert body["department"] == "vfx"
        assert body["status"] == TicketStatus.PENDING_REVIEW
        assert _ticket_count(_isolated_db) == 1

    def test_vfx_ticket_appears_in_list(self, client: TestClient, _isolated_db):
        with patch(
            "app.api.ingestion.gemini_classifier.classify",
            return_value=_ticket_create(Department.VFX),
        ):
            resp = client.post(
                "/api/v1/ingestion/director-notes",
                json={"shot_id": "SC01-SH001", "director_note": "Remove the boom mic."},
            )
        ticket_id = resp.json()["id"]
        list_resp = client.get("/api/v1/tickets")
        assert any(t["id"] == ticket_id for t in list_resp.json())


# ---------------------------------------------------------------------------
# 2. Sound note creates a ticket in the sound department
# ---------------------------------------------------------------------------

class TestSoundNoteCreatesTicket:
    def test_sound_json_returns_201_in_sound_department(self, client: TestClient, _isolated_db):
        with patch(
            "app.api.ingestion.gemini_classifier.classify",
            return_value=_ticket_create(Department.SOUND, Priority.MEDIUM),
        ):
            resp = client.post(
                "/api/v1/ingestion/director-notes",
                json={"shot_id": "SC02-SH005", "director_note": "El diálogo de la escena tiene eco excesivo."},
            )

        assert resp.status_code == 201
        body = resp.json()
        assert body["department"] == "sound"
        assert body["priority"] == "medium"
        assert _ticket_count(_isolated_db) == 1

    def test_sound_multipart_returns_201(self, client: TestClient, _isolated_db):
        with patch(
            "app.api.ingestion.gemini_classifier.classify",
            return_value=_ticket_create(Department.SOUND),
        ):
            resp = client.post(
                "/api/v1/ingestion/director-notes",
                data={"shot_id": "SC02-SH005", "director_note": "Eco excesivo en el diálogo."},
            )
        assert resp.status_code == 201
        assert resp.json()["department"] == "sound"


# ---------------------------------------------------------------------------
# 3. Colour note creates a ticket in the color department
# ---------------------------------------------------------------------------

class TestColourNoteCreatesTicket:
    def test_color_json_returns_201_in_color_department(self, client: TestClient, _isolated_db):
        with patch(
            "app.api.ingestion.gemini_classifier.classify",
            return_value=_ticket_create(Department.COLOR, Priority.CRITICAL),
        ):
            resp = client.post(
                "/api/v1/ingestion/director-notes",
                json={"shot_id": "SC04-SH010", "director_note": "El cielo necesita corrección de color hacia tonos cálidos."},
            )

        assert resp.status_code == 201
        body = resp.json()
        assert body["department"] == "color"
        assert body["priority"] == "critical"
        assert _ticket_count(_isolated_db) == 1


# ---------------------------------------------------------------------------
# 4. Catering note — no ticket, no SQLite record
# ---------------------------------------------------------------------------

class TestCateringNoteIsRejected:
    def test_catering_returns_200_not_201(self, client: TestClient, _isolated_db):
        with patch(
            "app.api.ingestion.gemini_classifier.classify",
            return_value=_REJECTION,
        ):
            resp = client.post(
                "/api/v1/ingestion/director-notes",
                json={"shot_id": "SC01-SH001", "director_note": "El catering llegó tarde al set."},
            )

        assert resp.status_code == 200

    def test_catering_response_has_correct_shape(self, client: TestClient, _isolated_db):
        with patch(
            "app.api.ingestion.gemini_classifier.classify",
            return_value=_REJECTION,
        ):
            resp = client.post(
                "/api/v1/ingestion/director-notes",
                json={"shot_id": "SC01-SH001", "director_note": "El catering llegó tarde al set."},
            )
        body = resp.json()
        assert body["requires_postproduction"] is False
        assert "ai_rationale" in body

    def test_catering_does_not_create_sqlite_record(self, client: TestClient, _isolated_db):
        with patch(
            "app.api.ingestion.gemini_classifier.classify",
            return_value=_REJECTION,
        ):
            client.post(
                "/api/v1/ingestion/director-notes",
                json={"shot_id": "SC01-SH001", "director_note": "El catering llegó tarde al set."},
            )
        assert _ticket_count(_isolated_db) == 0

    def test_catering_ticket_not_in_list(self, client: TestClient, _isolated_db):
        with patch(
            "app.api.ingestion.gemini_classifier.classify",
            return_value=_REJECTION,
        ):
            client.post(
                "/api/v1/ingestion/director-notes",
                json={"shot_id": "SC01-SH001", "director_note": "El catering llegó tarde al set."},
            )
        list_resp = client.get("/api/v1/tickets")
        assert list_resp.json() == []


# ---------------------------------------------------------------------------
# 5. Irrelevant note WITH a frame also does not create a ticket
# ---------------------------------------------------------------------------

class TestIrrelevantNoteWithFrameIsRejected:
    def test_irrelevant_with_frame_returns_200(self, client: TestClient, _isolated_db):
        with patch(
            "app.api.ingestion.gemini_classifier.classify_with_image",
            return_value=_REJECTION,
        ):
            resp = client.post(
                "/api/v1/ingestion/director-notes",
                data={"shot_id": "SC01-SH001", "director_note": "Buen trabajo a todo el equipo."},
                files={"frame": ("frame.png", io.BytesIO(_TINY_PNG), "image/png")},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["requires_postproduction"] is False

    def test_irrelevant_with_frame_no_sqlite_record(self, client: TestClient, _isolated_db):
        with patch(
            "app.api.ingestion.gemini_classifier.classify_with_image",
            return_value=_REJECTION,
        ):
            client.post(
                "/api/v1/ingestion/director-notes",
                data={"shot_id": "SC01-SH001", "director_note": "Buen trabajo a todo el equipo."},
                files={"frame": ("frame.png", io.BytesIO(_TINY_PNG), "image/png")},
            )
        assert _ticket_count(_isolated_db) == 0


# ---------------------------------------------------------------------------
# 6. The 200-rejection response does not break the frontend contract
# ---------------------------------------------------------------------------

class TestRejectionResponseShape:
    """The frontend must be able to safely read these fields from a 200 response."""

    def test_rejection_has_requires_postproduction_false(self, client: TestClient):
        with patch(
            "app.api.ingestion.gemini_classifier.classify",
            return_value=EligibilityRejection(
                requires_postproduction=False,
                ai_rationale="Horario de transporte, no postproducción.",
                rejection_reason="transporte",
            ),
        ):
            resp = client.post(
                "/api/v1/ingestion/director-notes",
                json={"shot_id": "SC01-SH001", "director_note": "El bus llega a las 8."},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["requires_postproduction"] is False
        assert isinstance(body["ai_rationale"], str)
        assert body["rejection_reason"] == "transporte"

    def test_rejection_has_no_ticket_fields(self, client: TestClient):
        """Fields that belong to Ticket (id, department, priority…) must be absent."""
        with patch(
            "app.api.ingestion.gemini_classifier.classify",
            return_value=_REJECTION,
        ):
            resp = client.post(
                "/api/v1/ingestion/director-notes",
                json={"shot_id": "SC01-SH001", "director_note": "Catering."},
            )
        body = resp.json()
        for ticket_only_field in ("id", "department", "priority", "status", "created_at"):
            assert ticket_only_field not in body, f"'{ticket_only_field}' should not be in rejection"

    def test_rejection_reason_may_be_null(self, client: TestClient):
        with patch(
            "app.api.ingestion.gemini_classifier.classify",
            return_value=EligibilityRejection(
                requires_postproduction=False,
                ai_rationale="La nota no aplica.",
                rejection_reason=None,
            ),
        ):
            resp = client.post(
                "/api/v1/ingestion/director-notes",
                json={"shot_id": "SC01-SH001", "director_note": "Hola a todos."},
            )
        assert resp.status_code == 200
        assert resp.json()["rejection_reason"] is None


# ---------------------------------------------------------------------------
# 7. Contract compatibility — JSON, multipart, URL-encoded all respect eligibility
# ---------------------------------------------------------------------------

class TestEligibilityAcrossContracts:
    def test_json_relevant_note_creates_ticket(self, client: TestClient, _isolated_db):
        with patch(
            "app.api.ingestion.gemini_classifier.classify",
            return_value=_ticket_create(Department.EDITORIAL),
        ):
            resp = client.post(
                "/api/v1/ingestion/director-notes",
                json={"shot_id": "SC01-SH001", "director_note": "Cut scene 3 before scene 4."},
            )
        assert resp.status_code == 201
        assert resp.json()["department"] == "editorial"
        assert _ticket_count(_isolated_db) == 1

    def test_multipart_relevant_note_creates_ticket(self, client: TestClient, _isolated_db):
        with patch(
            "app.api.ingestion.gemini_classifier.classify",
            return_value=_ticket_create(Department.VFX),
        ):
            resp = client.post(
                "/api/v1/ingestion/director-notes",
                data={"shot_id": "SC01-SH001", "director_note": "Remove crane from frame."},
            )
        assert resp.status_code == 201
        assert _ticket_count(_isolated_db) == 1

    def test_url_encoded_relevant_note_creates_ticket(self, client: TestClient, _isolated_db):
        with patch(
            "app.api.ingestion.gemini_classifier.classify",
            return_value=_ticket_create(Department.COLOR),
        ):
            resp = client.post(
                "/api/v1/ingestion/director-notes",
                content=b"shot_id=SC01-SH001&director_note=Fix+colour+grade.",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        assert resp.status_code == 201
        assert _ticket_count(_isolated_db) == 1

    def test_json_irrelevant_note_returns_200(self, client: TestClient, _isolated_db):
        with patch(
            "app.api.ingestion.gemini_classifier.classify",
            return_value=_REJECTION,
        ):
            resp = client.post(
                "/api/v1/ingestion/director-notes",
                json={"shot_id": "SC01-SH001", "director_note": "El catering llegó tarde."},
            )
        assert resp.status_code == 200
        assert _ticket_count(_isolated_db) == 0

    def test_multipart_irrelevant_note_returns_200(self, client: TestClient, _isolated_db):
        with patch(
            "app.api.ingestion.gemini_classifier.classify",
            return_value=_REJECTION,
        ):
            resp = client.post(
                "/api/v1/ingestion/director-notes",
                data={"shot_id": "SC01-SH001", "director_note": "El catering llegó tarde."},
            )
        assert resp.status_code == 200
        assert _ticket_count(_isolated_db) == 0

    def test_multipart_with_image_irrelevant_returns_200_no_db(self, client: TestClient, _isolated_db):
        with patch(
            "app.api.ingestion.gemini_classifier.classify_with_image",
            return_value=_REJECTION,
        ):
            resp = client.post(
                "/api/v1/ingestion/director-notes",
                data={"shot_id": "SC01-SH001", "director_note": "Felicitaciones al equipo."},
                files={"frame": ("frame.png", io.BytesIO(_TINY_PNG), "image/png")},
            )
        assert resp.status_code == 200
        assert _ticket_count(_isolated_db) == 0

    def test_multipart_with_image_relevant_creates_ticket(self, client: TestClient, _isolated_db):
        with patch(
            "app.api.ingestion.gemini_classifier.classify_with_image",
            return_value=_ticket_create(Department.VFX),
        ):
            resp = client.post(
                "/api/v1/ingestion/director-notes",
                data={"shot_id": "SC01-SH001", "director_note": "Remove the crane."},
                files={"frame": ("frame.png", io.BytesIO(_TINY_PNG), "image/png")},
            )
        assert resp.status_code == 201
        assert resp.json()["department"] == "vfx"
        assert _ticket_count(_isolated_db) == 1
