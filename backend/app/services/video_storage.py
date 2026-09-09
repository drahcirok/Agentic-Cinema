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

import logging
import re
import uuid
from typing import TYPE_CHECKING

from app.core.config import settings

_log = logging.getLogger(__name__)

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
_EVIDENCE_PREFIX = "deliveries/evidence"
_AVATAR_PREFIX = "profiles/avatars"
ALLOWED_EVIDENCE_MIME_TYPES: frozenset[str] = frozenset({"image/jpeg", "image/png", "image/webp", "application/pdf"})
MAX_EVIDENCE_SIZE_BYTES: int = 5 * 1024 * 1024
ALLOWED_AVATAR_MIME_TYPES: frozenset[str] = frozenset({"image/jpeg", "image/png", "image/webp"})
MAX_AVATAR_SIZE_BYTES: int = 2 * 1024 * 1024

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
        # Use provided bucket_name when given (even ""), fall back to settings
        # only when the argument is the sentinel None.
        self._bucket_name = (
            settings.google_cloud_storage_bucket if bucket_name is None else bucket_name
        )
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

        This is a **best-effort, fire-and-forget** cleanup call — it never
        raises to the caller under any circumstances.  All outcomes are logged
        at WARNING level (object path + exception type only; no credentials,
        tokens, video content or environment variables are ever recorded).

        Idempotent: if the object no longer exists the call is silently ignored.

        Parameters
        ----------
        gs_uri:
            A ``gs://<bucket>/<object>`` URI returned by :meth:`upload_video`.
        """
        # Derive a safe object_name early so we can use it in log messages even
        # when URI parsing fails.  Default to the raw URI if parsing is not
        # possible; the path component is still safe to log (no credentials).
        object_name: str = gs_uri  # fallback before parsing

        try:
            if not gs_uri.startswith("gs://"):
                _log.warning(
                    "GCS cleanup skipped: URI does not start with 'gs://' "
                    "(uri type: %s).",
                    type(gs_uri).__name__,
                )
                return

            # Parse gs://bucket/object/name
            without_scheme = gs_uri[len("gs://"):]
            slash_pos = without_scheme.find("/")
            if slash_pos == -1:
                _log.warning(
                    "GCS cleanup skipped: URI has no object path component."
                )
                return

            uri_bucket = without_scheme[:slash_pos]
            object_name = without_scheme[slash_pos + 1:]

            if not self._bucket_name:
                _log.warning(
                    "GCS cleanup skipped: bucket not configured "
                    "(object path: %r).",
                    object_name,
                )
                return

            if uri_bucket != self._bucket_name:
                _log.warning(
                    "GCS cleanup skipped: URI bucket does not match configured "
                    "bucket (object path: %r).",
                    object_name,
                )
                return

            bucket = self._get_bucket()
            blob = bucket.blob(object_name)
            try:
                blob.delete()
            except Exception as exc:
                # Import lazily — same pattern as _get_client().
                try:
                    from google.cloud.exceptions import NotFound

                    if isinstance(exc, NotFound):
                        # Object already gone — idempotent, not an error.
                        return
                except ImportError:
                    pass
                # Any other GCS error: log type + object path only.
                # Never log exception messages — they may contain tokens.
                _log.warning(
                    "GCS cleanup warning: could not delete object %r "
                    "(exception type: %s). "
                    "The temporary object may require manual removal.",
                    object_name,
                    type(exc).__name__,
                )

        except Exception as exc:  # pragma: no cover — last-resort safety net
            # An unexpected error in our own logic (e.g. attribute error).
            # Log type only — never the message.
            _log.warning(
                "GCS cleanup encountered an unexpected error "
                "(exception type: %s, object path: %r). "
                "Primary operation is unaffected.",
                type(exc).__name__,
                object_name,
            )

    def upload_evidence(self, data: bytes, mime_type: str, extension: str) -> str:
        """Store a small, private QC evidence file and return its GCS URI."""
        if mime_type not in ALLOWED_EVIDENCE_MIME_TYPES:
            raise ValueError("The file must be a JPG, PNG, or WEBP image, or a PDF.")
        if len(data) > MAX_EVIDENCE_SIZE_BYTES:
            raise ValueError("The evidence cannot exceed 5 MB.")
        if not is_safe_object_name(extension):
            raise ValueError("The file extension is invalid.")
        object_name = f"{_EVIDENCE_PREFIX}/{uuid.uuid4()}.{extension.lower()}"
        blob = self._get_bucket().blob(object_name)
        blob.upload_from_string(data, content_type=mime_type)
        return f"gs://{self._bucket_name}/{object_name}"

    def download_evidence(self, gs_uri: str) -> bytes:
        """Read only objects written by :meth:`upload_evidence`."""
        expected_prefix = f"gs://{self._bucket_name}/{_EVIDENCE_PREFIX}/"
        if not self._bucket_name or not gs_uri.startswith(expected_prefix):
            raise ValueError("The requested evidence is invalid.")
        object_name = gs_uri[len(f"gs://{self._bucket_name}/"):]
        return self._get_bucket().blob(object_name).download_as_bytes()

    def upload_avatar(self, data: bytes, mime_type: str, extension: str) -> str:
        """Store a small private profile image and return its GCS URI."""
        if mime_type not in ALLOWED_AVATAR_MIME_TYPES:
            raise ValueError("The photo must be a JPG, PNG, or WEBP image.")
        if not data:
            raise ValueError("The photo is empty.")
        if len(data) > MAX_AVATAR_SIZE_BYTES:
            raise ValueError("The photo cannot exceed 2 MB.")
        if not is_safe_object_name(extension):
            raise ValueError("The photo's file extension is invalid.")
        object_name = f"{_AVATAR_PREFIX}/{uuid.uuid4()}.{extension.lower()}"
        blob = self._get_bucket().blob(object_name)
        blob.upload_from_string(data, content_type=mime_type)
        return f"gs://{self._bucket_name}/{object_name}"

    def download_avatar(self, gs_uri: str) -> bytes:
        """Read only private objects stored by :meth:`upload_avatar`."""
        expected_prefix = f"gs://{self._bucket_name}/{_AVATAR_PREFIX}/"
        if not self._bucket_name or not gs_uri.startswith(expected_prefix):
            raise ValueError("The requested profile photo is invalid.")
        object_name = gs_uri[len(f"gs://{self._bucket_name}/"):]
        return self._get_bucket().blob(object_name).download_as_bytes()


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class StorageConfigurationError(Exception):
    """Raised when the GCS bucket is not configured."""


# ---------------------------------------------------------------------------
# Module-level singleton — wired to settings, overridable in tests
# ---------------------------------------------------------------------------

video_storage = VideoStorageService()
