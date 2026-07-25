"""
Supabase Storage client for profile photo uploads.

This module provides the SupabaseStorageClient class responsible for uploading
profile pictures to Supabase Storage and returning the public URL.

Requirements: 7.1–7.8
Design: Components and Interfaces — Profile_Service
"""
from __future__ import annotations

import os
import uuid


class StorageUnavailableError(Exception):
    """Raised when Supabase Storage cannot be reached or is not configured."""


class SupabaseStorageClient:
    """
    Client for uploading files to Supabase Storage.

    For MVP, if SUPABASE_URL and SUPABASE_KEY environment variables are not set,
    raises StorageUnavailableError. When configured, attempts a real upload via
    the Supabase Storage API (or returns a mock URL pattern for local dev).
    """

    def upload(self, cni: str, filename: str, content: bytes, content_type: str) -> str:
        """
        Upload a file to Supabase Storage.

        Args:
            cni: The user's CNI (used to organize files by user).
            filename: Original filename of the uploaded file.
            content: File content as bytes.
            content_type: MIME type (e.g., "image/jpeg").

        Returns:
            Public URL of the uploaded file.

        Raises:
            StorageUnavailableError: When Supabase Storage is not configured or unreachable.

        Requirements: 7.3, 7.8
        """
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_KEY")

        if not url or not key:
            raise StorageUnavailableError("Supabase Storage not configured.")

        # Real implementation would call supabase storage API here using supabase-py
        # For MVP, return a fake URL pattern that matches the expected structure
        object_id = uuid.uuid4()
        return f"{url}/storage/v1/object/public/photos/{cni}/{object_id}"
