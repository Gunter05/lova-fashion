"""
Supabase Storage helpers for the Fabric Catalog (Module 3) and Pattern Catalog
(Module 4).

Module 3 — ``upload_fabric_photo`` uploads a fabric photo to the
``fabric-photos`` bucket and returns its public URL.

Module 4 — ``upload_inspiration_image`` uploads a garment inspiration image to
the inspiration-images bucket (env: ``INSPIRATION_IMAGES_BUCKET``, default
``"inspiration-images"``) and returns its public URL.  ``delete_image``
performs a best-effort deletion of an image given its public URL — it never
raises so it is safe to call inside error-handling paths.

Environment variables required:
    SUPABASE_URL              — e.g. https://xxxxx.supabase.co
    SUPABASE_SERVICE_KEY      — service-role key (bypasses row-level security)

Environment variables optional:
    INSPIRATION_IMAGES_BUCKET — bucket name for inspiration images
                                (default: "inspiration-images")
"""

import logging
import os
from uuid import uuid4

from dotenv import load_dotenv
from supabase import create_client, Client

logger = logging.getLogger(__name__)

load_dotenv()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BUCKET_NAME = "fabric_photos"
CAPTURE_BUCKET_NAME = "photos_capture"

# Map common MIME types to file extensions used when building the storage path.
_CONTENT_TYPE_TO_EXT: dict[str, str] = {
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/png": "png",
    "image/gif": "gif",
    "image/webp": "webp",
    "image/bmp": "bmp",
    "image/tiff": "tiff",
    "image/svg+xml": "svg",
}


# ---------------------------------------------------------------------------
# Exception
# ---------------------------------------------------------------------------


class StorageUploadError(Exception):
    """Raised when uploading a file to Supabase Storage fails.

    The original exception is available via the ``__cause__`` attribute
    when the error wraps an underlying exception.
    """


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_supabase_client() -> Client:
    """Build and return a Supabase client using env-var credentials.

    Raises:
        StorageUploadError: if SUPABASE_URL or SUPABASE_SERVICE_KEY are not set.
    """
    url = os.environ.get("SUPABASE_URL", "").strip()
    key = (os.environ.get("SUPABASE_SERVICE_KEY") or os.environ.get("SUPABASE_KEY") or "").strip()

    if not url or not key:
        raise StorageUploadError(
            "SUPABASE_URL and SUPABASE_SERVICE_KEY environment variables must be set."
        )

    return create_client(url, key)


def _ext_from_content_type(content_type: str) -> str:
    """Return a file extension for *content_type*, defaulting to ``'bin'``."""
    # Normalise to lower-case; strip any parameter (e.g. "; charset=utf-8")
    base = content_type.split(";")[0].strip().lower()
    return _CONTENT_TYPE_TO_EXT.get(base, "bin")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def upload_fabric_photo(
    fabric_id: str,
    file_bytes: bytes,
    content_type: str,
) -> str:
    """Upload *file_bytes* to the ``fabric-photos`` Supabase Storage bucket.

    The file is stored at the path ``{fabric_id}/{uuid4()}.{ext}`` so that
    each upload gets a unique key and multiple photos per fabric are
    supported without collisions.  A new upload therefore does **not**
    overwrite the previous file at the object-storage level, but the
    ``fabric_photo`` column in the database is always overwritten with the
    latest URL (Req 6 AC5).

    Args:
        fabric_id:    String representation of the fabric's UUID.
        file_bytes:   Raw bytes of the image to upload.
        content_type: MIME type of the file (e.g. ``"image/jpeg"``).

    Returns:
        The public URL of the uploaded file as a string.

    Raises:
        StorageUploadError: if the upload fails for any reason (missing env
            vars, network error, Supabase API error, etc.).
    """
    try:
        client: Client = _get_supabase_client()
    except StorageUploadError:
        raise

    ext = _ext_from_content_type(content_type)
    file_path = f"{fabric_id}/{uuid4()}.{ext}"

    try:
        client.storage.from_(BUCKET_NAME).upload(
            path=file_path,
            file=file_bytes,
            file_options={"content-type": content_type},
        )
    except Exception as exc:
        raise StorageUploadError(
            f"Failed to upload photo for fabric '{fabric_id}': {exc}"
        ) from exc

    try:
        public_url: str = client.storage.from_(BUCKET_NAME).get_public_url(file_path)
    except Exception as exc:
        raise StorageUploadError(
            f"Upload succeeded but could not retrieve public URL for '{file_path}': {exc}"
        ) from exc

    return public_url



async def upload_capture_photo(
    session_id: str,
    view: str,
    file_bytes: bytes,
    content_type: str,
) -> str:
    """Upload a measurement capture photo (face or profile) to the ``photos_capture`` bucket.

    Args:
        session_id:   UUID of the measurement session.
        view:         Either ``"face"`` or ``"profile"``.
        file_bytes:   Raw bytes of the image.
        content_type: MIME type of the file.

    Returns:
        The public URL of the uploaded file.

    Raises:
        StorageUploadError: if the upload fails.
    """
    try:
        client: Client = _get_supabase_client()
    except StorageUploadError:
        raise

    ext = _ext_from_content_type(content_type)
    file_path = f"{session_id}/{view}/{uuid4()}.{ext}"

    try:
        client.storage.from_(CAPTURE_BUCKET_NAME).upload(
            path=file_path,
            file=file_bytes,
            file_options={"content-type": content_type},
        )
    except Exception as exc:
        raise StorageUploadError(
            f"Failed to upload {view} capture photo for session '{session_id}': {exc}"
        ) from exc

    try:
        public_url: str = client.storage.from_(CAPTURE_BUCKET_NAME).get_public_url(file_path)
    except Exception as exc:
        raise StorageUploadError(
            f"Upload succeeded but could not retrieve public URL for '{file_path}': {exc}"
        ) from exc

    return public_url


# ---------------------------------------------------------------------------
# Module 4 — Pattern Catalog: inspiration-image helpers
# ---------------------------------------------------------------------------

# Bucket name read from the environment; falls back to a sensible default.
INSPIRATION_IMAGES_BUCKET: str = os.environ.get(
    "INSPIRATION_IMAGES_BUCKET", "inspiration-images"
)


def upload_inspiration_image(file_bytes: bytes, filename: str) -> str:
    """Upload an inspiration image to Supabase Storage and return its public URL.

    The image is stored at ``{uuid4()}/{filename}`` so every upload gets a
    unique, collision-free path even when two clients submit the same filename.

    Args:
        file_bytes: Raw bytes of the image file to upload.
        filename:   Original filename (e.g. ``"photo.jpg"``).  Used as the
                    leaf component of the storage path and to infer the
                    Content-Type header.

    Returns:
        The publicly accessible URL of the uploaded image as a string.

    Raises:
        StorageUploadError: if the upload fails for any reason — missing env
            vars, network error, Supabase API error, or failure to retrieve
            the public URL.  The caller (``POST /models/init``) maps this to
            HTTP 500 (Req 1 AC7).
    """
    try:
        client: Client = _get_supabase_client()
    except StorageUploadError:
        raise

    # Build a unique path: <random-uuid>/<original-filename>
    unique_dir = str(uuid4())
    file_path = f"{unique_dir}/{filename}"

    # Derive a Content-Type from the file extension so Supabase serves the
    # object with the correct MIME type.
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    _ext_to_mime: dict[str, str] = {
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "webp": "image/webp",
    }
    content_type = _ext_to_mime.get(ext, "application/octet-stream")

    try:
        client.storage.from_(INSPIRATION_IMAGES_BUCKET).upload(
            path=file_path,
            file=file_bytes,
            file_options={"content-type": content_type},
        )
    except Exception as exc:
        raise StorageUploadError(
            f"Failed to upload inspiration image '{filename}' to bucket "
            f"'{INSPIRATION_IMAGES_BUCKET}': {exc}"
        ) from exc

    try:
        public_url: str = client.storage.from_(INSPIRATION_IMAGES_BUCKET).get_public_url(
            file_path
        )
    except Exception as exc:
        raise StorageUploadError(
            f"Upload of '{filename}' succeeded but could not retrieve public URL "
            f"for path '{file_path}': {exc}"
        ) from exc

    return public_url


def delete_image(photo_url: str) -> None:
    """Best-effort deletion of an inspiration image from Supabase Storage.

    This function is called when the AI Analyzer step fails after a successful
    image upload (design §5) — the orphaned image must be cleaned up before
    returning the error response to the client.

    **This function never raises.**  Any exception is logged at WARNING level
    and silently swallowed so that the caller's error response is not masked
    by a secondary storage failure.

    Args:
        photo_url: The full public URL returned by ``upload_inspiration_image``.
                   The storage path is extracted from the URL by stripping the
                   bucket-specific prefix.
    """
    try:
        client: Client = _get_supabase_client()
    except Exception as exc:
        logger.warning(
            "delete_image: could not build Supabase client, skipping cleanup "
            "for '%s': %s",
            photo_url,
            exc,
        )
        return

    # Extract the object path from the public URL.
    # Supabase public URLs have the form:
    #   https://<project>.supabase.co/storage/v1/object/public/<bucket>/<path>
    # We need everything after ``/public/<bucket>/``.
    bucket_prefix = f"/object/public/{INSPIRATION_IMAGES_BUCKET}/"
    try:
        idx = photo_url.index(bucket_prefix)
        file_path = photo_url[idx + len(bucket_prefix):]
    except ValueError:
        logger.warning(
            "delete_image: could not parse storage path from URL '%s', "
            "skipping cleanup.",
            photo_url,
        )
        return

    if not file_path:
        logger.warning(
            "delete_image: extracted empty path from URL '%s', skipping cleanup.",
            photo_url,
        )
        return

    try:
        client.storage.from_(INSPIRATION_IMAGES_BUCKET).remove([file_path])
        logger.info("delete_image: removed orphaned image '%s'.", file_path)
    except Exception as exc:
        logger.warning(
            "delete_image: failed to remove '%s' from bucket '%s': %s",
            file_path,
            INSPIRATION_IMAGES_BUCKET,
            exc,
        )
