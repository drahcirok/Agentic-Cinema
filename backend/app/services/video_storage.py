"""Video storage service for FrameFlow.

Uploads reference video files to Google Cloud Storage and returns a gs:// URI
that can later be passed to Gemini's multimodal API.

Design decisions
----------------
- Uses ADC (Application Default Credentials) automatically — no API key needed.
  On Cloud Run the service account attached to the revision is used. Locally,
  ``gcloud auth application-default login`` provides credentials.
- The GCS client is created lazily on first call so that unit tests can inject a
  mock before any real network I/O occurs.
- Object names are always UUID-based to avoid path traversal and collisions.
- Uploaded objects live under ``uploads/videos/`` and are meant to be
  short-lived; callers should delete them after Gemini finishes processing.

IAM requirements for the Cloud Run service account on the bucket
----------------------------------------------------------------
The following roles (or equivalent custom permissions) are required:

  roles/storage.objectCreator
      - storage.objects.create
      Needed to upload new video objects.

  roles/storage.objectViewer   (only if the service reads back the object)
      - storage.objects.get
      Needed to generate signed URLs or verify uploads (optional for this service).

  storage.objects.delete       (via roles/storage.objectAdmin or a custom role)
      Needed to clean up temporary uploads after Gemini processes them.

Minimal custom role permissions:
    storage.objects.create
    storage.objects.delete

Grant these at the BUCKET level (not project level) to follow least-privilege:
    gcloud storage buckets add-iam-policy-binding gs://BUCKET_NAME \\
        --member="serviceAccount:SA_EMAIL" \\
        --role="roles/storage.objectCreator"

    # For deletion, use a custom role or roles/storage.objectAdmin scoped to the bucket:
    gcloud storage buckets add-iam-policy-binding gs://BUCKET_NAME \\
        --member="serviceAccount:SA_EMAIL" \\
        --role="roles/storage.objectAdmin"
"""

from __future__ import annotations

import re
import uuid
from typing import TYPE_CHECKING

from app.core.config import settings

if TYPE_CHECKING:
    # Avoid importing the heavy GCS SDK at module load time in tests that do
    # not exercise storage paths.
    from google.cloud import storage as gcs_module

# ---------------------------------------------------------------------------
# Constants — shared with the future upload endpoint and tests
# ---------------------------------------------------------------------------

#: MIME types accepted for video uploads.
ALLOWED_VIDEO_MIME_TYPES: frozenset[str] = frozenset({"video/mp4"})

#: Maximum accepted video size in bytes (50 MiB).
MAX_VIDEO_SIZE_BYTES: int = 50 * 1024 * 1024

#: GCS object prefix under which all uploaded videos are stored.
_UPLOAD_PREFIX = "uploads/videos"

#: Only characters that are safe in GCS object names and unambiguous in URIs.
_SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9_\-\.]+$")


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def is_safe_object_name(name: str) -> bool:
    """Return True if *name* contains only URI-safe characters.

    This is a conservative allow-list: letters, digits, hyphens, underscores
    and dots.  It deliberately rejects slashes and other special characters so
    that callers cannot escape the ``_UPLOAD_PREFIX`` by injecting path
    components.
    """
    return bool(_SAFE_NAME_RE.match(name))


# ---------------------------------------------------------------------------
# VideoStorageService
# ---------------------------------------------------------------------------


class VideoStorageService:
    """Manages temporary video uploads to Google Cloud Storage.

    Parameters
    ----------
    bucket_name:
        GCS bucket name.  Defaults to ``settings.google_cloud_storage_bucket``.
    client:
        Injected ``google.cloud.storage.Client`` instance.  Pass a mock in
        tests; leave ``None`` in production to use the real ADC-authenticated
        client.
    """

    def __init__(
        self,
        bucket_name: str | None = None,
        client: "gcs_module.Client | None" = None,
    ) -> None:
        self._bucket_name = bucket_name or settings.google_cloud_storage_bucket
        self._client = client  # None → created lazily on first use

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _get_client(self) -> "gcs_module.Client":
        if self._client is None:
            from google.cloud import storage as gcs

            # ADC is resolved automatically; no explicit credentials argument.
            self._client = gcs.Client(project=settings.google_cloud_project)
        return self._client

    def _get_bucket(self) -> "gcs_module.Bucket":
        if not self._bucket_name:
            raise StorageConfigurationError(
                "GOOGLE_CLOUD_STORAGE_BUCKET is not configured. "
                "Set it in .env or as an environment variable."
            )
        return self._get_client().bucket(self._bucket_name)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def upload_video(
        self,
        data: bytes,
        mime_type: str,
        extension: str = "mp4",
    ) -> str:
        """Upload *data* to GCS and return its ``gs://`` URI.

        Parameters
        ----------
        data:
            Raw video bytes.
        mime_type:
            MIME type of the video (e.g. ``"video/mp4"``).
        extension:
            File extension used in the object name, without the leading dot.
            Must match ``_SAFE_NAME_RE`` (alphanumeric, hyphens, underscores, dots).

        Returns
        -------
        str
            A ``gs://<bucket>/<prefix>/<uuid>.<ext>`` URI.

        Raises
        ------
        StorageConfigurationError
            If the bucket name is not configured.
        ValueError
            If *extension* contains unsafe characters.
        """
        if not is_safe_object_name(extension):
            raise ValueError(
                f"Unsafe file extension: {extension!r}. "
                "Only alphanumeric characters, hyphens, underscores and dots are allowed."
            )

        object_name = f"{_UPLOAD_PREFIX}/{uuid.uuid4()}.{extension}"
        bucket = self._get_bucket()
        blob = bucket.blob(object_name)
        blob.upload_from_string(data, content_type=mime_type)
        return f"gs://{self._bucket_name}/{object_name}"

    def delete_object(self, gs_uri: str) -> None:
        """Delete the GCS object identified by *gs_uri*.

        This is a best-effort cleanup call.  If the object does not exist the
        call is silently ignored so that retry logic and idempotent cleanups
        work without special-casing.

        Parameters
        ----------
        gs_uri:
            A ``gs://<bucket>/<object>`` URI returned by :meth:`upload_video`.

        Raises
        ------
        StorageConfigurationError
            If the bucket name is not configured.
        ValueError
            If *gs_uri* does not start with ``gs://`` or refers to a different
            bucket than the one configured.
        """
        if not gs_uri.startswith("gs://"):
            raise ValueError(f"Invalid GCS URI: {gs_uri!r}. Must start with 'gs://'.")

        # Parse gs://bucket/object/name
        without_scheme = gs_uri[len("gs://"):]
        slash_pos = without_scheme.find("/")
        if slash_pos == -1:
            raise ValueError(f"Invalid GCS URI (no object path): {gs_uri!r}.")

        uri_bucket = without_scheme[:slash_pos]
        object_name = without_scheme[slash_pos + 1:]

        # Validate bucket configuration before any GCS call.
        if not self._bucket_name:
            raise StorageConfigurationError(
                "GOOGLE_CLOUD_STORAGE_BUCKET is not configured. "
                "Set it in .env or as an environment variable."
            )

        if uri_bucket != self._bucket_name:
            raise ValueError(
                f"URI bucket {uri_bucket!r} does not match configured bucket "
                f"{self._bucket_name!r}."
            )

        bucket = self._get_bucket()
        blob = bucket.blob(object_name)
        try:
            blob.delete()
        except Exception:  # noqa: BLE001 — object may already be gone
            pass


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class StorageConfigurationError(Exception):
    """Raised when the GCS bucket is not configured."""


# ---------------------------------------------------------------------------
# Module-level singleton — wired to settings, overridable in tests
# ---------------------------------------------------------------------------

video_storage = VideoStorageService()
