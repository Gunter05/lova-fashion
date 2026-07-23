"""
Supabase Storage adapter for Module 2 — Photo Capture & Measurement Estimation.
Tasks T-03.1, T-03.2 — Design §9

Storage path convention (enforced here, mirrors RLS policy):
    captures/{user_id}/{session_id}/front.jpg
    captures/{user_id}/{session_id}/profile.jpg

RLS bucket policy (applied via migration 004_storage_bucket_rls.sql):
    auth.uid()::text = (storage.foldername(name))[1]
This guarantees that each user can only read/write files under their own
user_id prefix. The path construction in upload() must never deviate from
this structure, or uploads will be silently rejected by the RLS policy.

Verification checklist (T-03.2):
  [x] Bucket 'captures' created as PRIVATE in Supabase dashboard.
  [x] Migration 004 applied — four RLS policies (SELECT / INSERT / UPDATE / DELETE)
      on storage.objects scoped to bucket_id = 'captures'.
  [x] Path template `{user_id}/{session_id}/{view}.jpg` places user_id at
      folder position [1], matching (storage.foldername(name))[1].
"""

import os
import uuid
from typing import Literal

import httpx
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


# Lazy-initialised so that import-time errors don't surface during testing
# without a real Supabase connection.
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
    Thin wrapper around the Supabase Python client for photo storage.

    All paths are constructed as:
        {user_id}/{session_id}/{view}.jpg
    inside the 'captures' bucket, satisfying the RLS policy documented above.
    """

    def __init__(self, bucket: str | None = None) -> None:
        self._bucket = bucket or os.environ.get("SUPABASE_STORAGE_BUCKET", "captures")

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
        Upload a photo to Supabase Storage.

        Parameters
        ----------
        user_id     : Owner's UUID — first path segment (for RLS matching).
        session_id  : Capture session UUID — second path segment.
        view        : 'front' or 'profile'.
        file_bytes  : Raw image bytes.
        mime_type   : 'image/jpeg' or 'image/png'.

        Returns
        -------
        str : Public URL of the uploaded file.

        Raises
        ------
        StorageUploadError : On any Supabase-side failure.
        """
        path = self._build_path(user_id, session_id, view, mime_type)
        client = _get_client()

        try:
            # upsert=True lets us overwrite on retry (AC-06.1)
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

        # Build the public URL from the Supabase project URL
        supabase_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
        public_url = (
            f"{supabase_url}/storage/v1/object/public/{self._bucket}/{path}"
        )
        return public_url

    # ------------------------------------------------------------------
    # download()
    # ------------------------------------------------------------------

    def download(self, url: str) -> bytes:
        """
        Download a photo from Supabase Storage by its public URL.

        Parameters
        ----------
        url : Full public URL as returned by upload().

        Returns
        -------
        bytes : Raw image bytes.

        Raises
        ------
        StorageDownloadError : On HTTP error or connection failure.
        """
        try:
            response = httpx.get(url, timeout=15.0)
            response.raise_for_status()
            return response.content
        except httpx.HTTPStatusError as exc:
            raise StorageDownloadError(
                f"Impossible de télécharger la photo (HTTP {exc.response.status_code}) : {url}"
            ) from exc
        except httpx.RequestError as exc:
            raise StorageDownloadError(
                f"Erreur réseau lors du téléchargement de la photo : {exc}"
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
        """
        Construct the storage path for a photo.

        Pattern: {user_id}/{session_id}/{view}.{ext}
        The first segment is user_id, matching the RLS expression:
            auth.uid()::text = (storage.foldername(name))[1]
        """
        ext = "jpg" if mime_type == "image/jpeg" else "png"
        return f"{user_id}/{session_id}/{view}.{ext}"
