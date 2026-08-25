"""Unit tests for VideoStorageService.

All Google Cloud Storage calls are mocked via unittest.mock so that no real
GCS credentials or network I/O are needed.

Test groups
-----------
TestSafeObjectName      — is_safe_object_name() helper
TestUploadVideo         — VideoStorageService.upload_video()
TestDeleteObject        — VideoStorageService.delete_object()
TestStorageConfiguration — misconfiguration paths
TestVideoConstants      — shared constants exported from the models layer
"""

from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest

from app.services.video_storage import (
    ALLOWED_VIDEO_MIME_TYPES,
    MAX_VIDEO_SIZE_BYTES,
    StorageConfigurationError,
    VideoStorageService,
    is_safe_object_name,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_service(bucket_name: str = "test-bucket") -> tuple[VideoStorageService, MagicMock]:
    """Return a (service, mock_bucket) pair.

    The mock_bucket is already wired so that bucket.blob(name).upload_from_string
    and blob.delete() are trackable.
    """
    mock_blob = MagicMock()
    mock_bucket = MagicMock()
    mock_bucket.blob.return_value = mock_blob

    mock_client = MagicMock()
    mock_client.bucket.return_value = mock_bucket

    svc = VideoStorageService(bucket_name=bucket_name, client=mock_client)
    return svc, mock_bucket, mock_blob


# ---------------------------------------------------------------------------
# TestSafeObjectName
# ---------------------------------------------------------------------------


class TestSafeObjectName:
    def test_alphanumeric_is_safe(self):
        assert is_safe_object_name("abc123") is True

    def test_hyphens_and_underscores_are_safe(self):
        assert is_safe_object_name("my-file_name") is True

    def test_dots_are_safe(self):
        assert is_safe_object_name("video.mp4") is True

    def test_uuid_with_extension_is_safe(self):
        assert is_safe_object_name("550e8400-e29b-41d4-a716-446655440000.mp4") is True

    def test_slash_is_unsafe(self):
        assert is_safe_object_name("../etc/passwd") is False

    def test_space_is_unsafe(self):
        assert is_safe_object_name("bad name.mp4") is False

    def test_empty_string_is_unsafe(self):
        assert is_safe_object_name("") is False

    def test_null_byte_is_unsafe(self):
        assert is_safe_object_name("file\x00.mp4") is False

    def test_question_mark_is_unsafe(self):
        assert is_safe_object_name("file?.mp4") is False


# ---------------------------------------------------------------------------
# TestUploadVideo
# ---------------------------------------------------------------------------


class TestUploadVideo:
    def test_returns_gs_uri(self):
        svc, mock_bucket, mock_blob = _make_service("my-bucket")
        uri = svc.upload_video(b"fake-mp4-bytes", "video/mp4")
        assert uri.startswith("gs://my-bucket/uploads/videos/")
        assert uri.endswith(".mp4")

    def test_uri_contains_uuid(self):
        import re

        svc, _, _ = _make_service()
        uri = svc.upload_video(b"bytes", "video/mp4")
        # Extract the filename portion and check it looks like a UUID
        filename = uri.rsplit("/", 1)[-1].replace(".mp4", "")
        uuid_re = re.compile(
            r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
        )
        assert uuid_re.match(filename), f"Expected UUID, got: {filename!r}"

    def test_calls_upload_from_string_with_correct_args(self):
        svc, mock_bucket, mock_blob = _make_service()
        data = b"\x00\x01\x02"
        svc.upload_video(data, "video/mp4")
        mock_blob.upload_from_string.assert_called_once_with(data, content_type="video/mp4")

    def test_blob_name_uses_upload_prefix(self):
        svc, mock_bucket, mock_blob = _make_service()
        svc.upload_video(b"bytes", "video/mp4")
        blob_name: str = mock_bucket.blob.call_args[0][0]
        assert blob_name.startswith("uploads/videos/")

    def test_custom_extension_is_used(self):
        svc, mock_bucket, _ = _make_service()
        uri = svc.upload_video(b"bytes", "video/mp4", extension="mp4")
        assert uri.endswith(".mp4")

    def test_unsafe_extension_raises_value_error(self):
        svc, _, _ = _make_service()
        with pytest.raises(ValueError, match="Unsafe file extension"):
            svc.upload_video(b"bytes", "video/mp4", extension="../evil")

    def test_extension_with_slash_raises_value_error(self):
        svc, _, _ = _make_service()
        with pytest.raises(ValueError):
            svc.upload_video(b"bytes", "video/mp4", extension="a/b")

    def test_two_uploads_produce_distinct_uris(self):
        svc, _, _ = _make_service()
        uri1 = svc.upload_video(b"bytes", "video/mp4")
        uri2 = svc.upload_video(b"bytes", "video/mp4")
        assert uri1 != uri2

    def test_raises_when_bucket_not_configured(self):
        svc = VideoStorageService(bucket_name=None, client=MagicMock())
        with pytest.raises(StorageConfigurationError):
            svc.upload_video(b"bytes", "video/mp4")


# ---------------------------------------------------------------------------
# TestDeleteObject
# ---------------------------------------------------------------------------


class TestDeleteObject:
    def test_deletes_correct_blob(self):
        svc, mock_bucket, mock_blob = _make_service("my-bucket")
        svc.delete_object("gs://my-bucket/uploads/videos/some-uuid.mp4")
        mock_bucket.blob.assert_called_once_with("uploads/videos/some-uuid.mp4")
        mock_blob.delete.assert_called_once()

    def test_delete_is_silent_when_object_missing(self):
        """GCS raises an exception if the object doesn't exist; the service
        must swallow it so that idempotent cleanups work."""
        svc, mock_bucket, mock_blob = _make_service("my-bucket")
        mock_blob.delete.side_effect = Exception("Not Found")
        # Must not raise
        svc.delete_object("gs://my-bucket/uploads/videos/gone.mp4")

    def test_raises_for_non_gs_uri(self):
        svc, _, _ = _make_service()
        with pytest.raises(ValueError, match="Invalid GCS URI"):
            svc.delete_object("https://storage.googleapis.com/bucket/object")

    def test_raises_for_uri_without_object_path(self):
        svc, _, _ = _make_service()
        with pytest.raises(ValueError, match="no object path"):
            svc.delete_object("gs://bucket-only")

    def test_raises_for_wrong_bucket(self):
        svc, _, _ = _make_service(bucket_name="correct-bucket")
        with pytest.raises(ValueError, match="does not match configured bucket"):
            svc.delete_object("gs://other-bucket/uploads/videos/file.mp4")

    def test_raises_when_bucket_not_configured(self):
        svc = VideoStorageService(bucket_name=None, client=MagicMock())
        with pytest.raises(StorageConfigurationError):
            svc.delete_object("gs://anything/path/file.mp4")


# ---------------------------------------------------------------------------
# TestStorageConfiguration
# ---------------------------------------------------------------------------


class TestStorageConfiguration:
    def test_lazy_client_creation_uses_adc(self):
        """When no client is injected, the service creates one via gcs.Client()
        which picks up ADC automatically.  We mock google.cloud.storage.Client
        at import time to avoid real I/O."""
        mock_blob = MagicMock()
        mock_bucket = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        mock_gcs_client = MagicMock()
        mock_gcs_client.bucket.return_value = mock_bucket

        svc = VideoStorageService(bucket_name="test-bucket", client=None)

        # Patch the Client class that _get_client() imports lazily.
        with patch("google.cloud.storage.Client", return_value=mock_gcs_client):
            uri = svc.upload_video(b"bytes", "video/mp4")

        assert uri.startswith("gs://test-bucket/")
        mock_gcs_client.bucket.assert_called_once_with("test-bucket")

    def test_validate_storage_raises_when_no_bucket(self):
        from app.core.config import Settings

        # Create a fresh Settings instance with no bucket set
        s = Settings(google_cloud_storage_bucket=None)
        with pytest.raises(ValueError, match="GOOGLE_CLOUD_STORAGE_BUCKET"):
            s.validate_storage()

    def test_validate_storage_passes_when_bucket_set(self):
        from app.core.config import Settings

        s = Settings(google_cloud_storage_bucket="my-bucket")
        s.validate_storage()  # Must not raise


# ---------------------------------------------------------------------------
# TestVideoConstants
# ---------------------------------------------------------------------------


class TestVideoConstants:
    def test_mp4_is_in_allowed_types(self):
        assert "video/mp4" in ALLOWED_VIDEO_MIME_TYPES

    def test_max_size_is_50_mib(self):
        assert MAX_VIDEO_SIZE_BYTES == 50 * 1024 * 1024

    def test_constants_exported_from_models_match_service(self):
        """The ingestion models re-export the same values so endpoints only
        need one import.  Check they stay in sync."""
        from app.models.ingestion import (
            ALLOWED_VIDEO_MIME_TYPES as MODEL_ALLOWED,
            MAX_VIDEO_SIZE_BYTES as MODEL_MAX,
        )

        assert MODEL_ALLOWED == ALLOWED_VIDEO_MIME_TYPES
        assert MODEL_MAX == MAX_VIDEO_SIZE_BYTES
