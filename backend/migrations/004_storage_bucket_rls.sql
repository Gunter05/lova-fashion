-- Migration 004 — Supabase Storage bucket and RLS for captures
-- Module 2 — Photo Capture & Measurement Estimation
-- Task T-03.2 — NFR-04, Design §9
--
-- Run this in the Supabase SQL editor AFTER creating the 'captures' bucket
-- via the Supabase dashboard (Storage → New bucket → name: captures, private: true).

-- RLS policy: a user may only read/write files under their own user_id folder.
-- The path structure enforced by storage.py is:
--   captures/{user_id}/{session_id}/front.jpg
--   captures/{user_id}/{session_id}/profile.jpg
--
-- (storage.foldername(name))[1] returns the first folder component of the file path.

CREATE POLICY storage_captures_owner_select
    ON storage.objects FOR SELECT
    USING (
        bucket_id = 'captures'
        AND auth.uid()::text = (storage.foldername(name))[1]
    );

CREATE POLICY storage_captures_owner_insert
    ON storage.objects FOR INSERT
    WITH CHECK (
        bucket_id = 'captures'
        AND auth.uid()::text = (storage.foldername(name))[1]
    );

CREATE POLICY storage_captures_owner_update
    ON storage.objects FOR UPDATE
    USING (
        bucket_id = 'captures'
        AND auth.uid()::text = (storage.foldername(name))[1]
    );

CREATE POLICY storage_captures_owner_delete
    ON storage.objects FOR DELETE
    USING (
        bucket_id = 'captures'
        AND auth.uid()::text = (storage.foldername(name))[1]
    );
