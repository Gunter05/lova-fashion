"""
Supabase Storage adapter for Module 2 — Photo Capture & Measurement Estimation.
Tasks T-03.1, T-03.2 — Design §9

Storage path convention (enforced here, mirrors RLS policy):
    photos_capture/{user_id}/{session_id}/front.jpg
    photos_capture/{user_id}/{session_id}/profile.jpg

The bucket is PRIVATE. Upload uses the service-role Supabase client (bypasses
RLS at the server level). Download also uses the Supabase client so it never
needs a public URL — the stored value is the storage path, not a public URL.
"""

import os
import uuid
from typing import Literal

from supabase import Client, create_client


# ---------------------------------------------------------------------------
# Supabase client — module-level singleton
# ---------------------------------------------------------------------------

def _make_supabase_client() -> Client:
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_KEY", "")
    if not url or not key:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_KEY must be set in environment variables."
        )
    return create_client(url, key)


_supabase_client: Client | None = None


def _get_client() -> Client:
    global _supabase_client
    if _supabase_client is None:
        _supabase_client = _make_supabase_client()
    return _supabase_client


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------

class StorageUploadError(Exception):
    """Raised when uploading a photo to Supabase Storage fails."""


class StorageDownloadError(Exception):
    """Raised when downloading a photo from Supabase Storage fails."""


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------

class SupabaseStorageAdapter:
    """
    Wraps Supabase Storage for private-bucket photo handling.

    upload() — stores the file and returns the storage PATH (not a public URL).
    download() — fetches bytes using the Supabase client (service-role key,
                 no public URL needed).
    """

    def __init__(self, bucket: str | None = None) -> None:
        self._bucket = bucket or os.environ.get("SUPABASE_STORAGE_BUCKET", "photos_capture")

    # ------------------------------------------------------------------
    # upload()
    # ------------------------------------------------------------------

    def upload(
        self,
        user_id: uuid.UUID,
        session_id: uuid.UUID,
        view: Literal["front", "profile"],
        file_bytes: bytes,
        mime_type: str,
    ) -> str:
        """
        Upload a photo and return its **storage path** (not a public URL).
        The path is what gets stored in capture_sessions.front_photo_url /
        profile_photo_url and passed back to download() later.
        """
        path = self._build_path(user_id, session_id, view, mime_type)
        client = _get_client()

        try:
            client.storage.from_(self._bucket).upload(
                path=path,
                file=file_bytes,
                file_options={
                    "content-type": mime_type,
                    "upsert": "true",
                },
            )
        except Exception as exc:
            raise StorageUploadError(
                f"Échec de l'upload de la photo ({view}) : {exc}"
            ) from exc

        # Return the path so the caller can store it and retrieve it later.
        # We do NOT build a /object/public/ URL because the bucket is private.
        return path

    # ------------------------------------------------------------------
    # download()
    # ------------------------------------------------------------------

    def download(self, path_or_url: str) -> bytes:
        """
        Download a photo using the Supabase client (service-role key).

        Accepts either:
        - a bare storage path  e.g. ``{user_id}/{session_id}/front.jpg``
        - a legacy full URL    e.g. ``https://xxx.supabase.co/storage/v1/...``
          (for backward compatibility with rows already in the DB)
        """
        # Normalise: extract the path portion if a full URL was stored
        path = self._extract_path(path_or_url)

        try:
            data: bytes = _get_client().storage.from_(self._bucket).download(path)
            return data
        except Exception as exc:
            raise StorageDownloadError(
                f"Impossible de télécharger la photo depuis Storage "
                f"(bucket={self._bucket}, path={path}) : {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_path(
        user_id: uuid.UUID,
        session_id: uuid.UUID,
        view: Literal["front", "profile"],
        mime_type: str,
    ) -> str:
        ext = "jpg" if mime_type == "image/jpeg" else "png"
        return f"{user_id}/{session_id}/{view}.{ext}"

    def _extract_path(self, path_or_url: str) -> str:
        """
        If path_or_url is a full Supabase Storage URL, strip everything up to
        and including the bucket name so we get a bare object path.
        Otherwise return as-is.
        """
        marker = f"/{self._bucket}/"
        if marker in path_or_url:
            return path_or_url.split(marker, 1)[1]
        return path_or_url
