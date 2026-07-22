"""
Supabase Storage helper for the Fabric Catalog module.

Provides a single async function that uploads a fabric photo to the
``fabric-photos`` bucket in Supabase Storage and returns its public URL.

Environment variables required:
    SUPABASE_URL         — e.g. https://xxxxx.supabase.co
    SUPABASE_SERVICE_KEY — service-role key (bypasses row-level security)
"""

import os
from uuid import uuid4

from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BUCKET_NAME = "fabric-photos"

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
    key = os.environ.get("SUPABASE_SERVICE_KEY", "").strip()

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
