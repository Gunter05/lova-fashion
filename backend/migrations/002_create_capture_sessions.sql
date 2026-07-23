-- Migration 002 — Create capture_sessions table
-- Module 2 — Photo Capture & Measurement Estimation
-- Task T-01.2 — AC-01.2, AC-01.3, AC-03.1, NFR-04, Design §3.1

CREATE TABLE capture_sessions (
    id                UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id           UUID          NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    status            VARCHAR(20)   NOT NULL DEFAULT 'empty'
                                    CHECK (status IN ('empty', 'processing', 'success', 'failed')),
    front_photo_url   TEXT,
    profile_photo_url TEXT,
    entered_stature   DECIMAL(5,1)
                      CHECK (entered_stature IS NULL OR (entered_stature >= 100 AND entered_stature <= 250)),
    is_active         BOOLEAN       NOT NULL DEFAULT FALSE,
    retry_count       INTEGER       NOT NULL DEFAULT 0,
    failure_reason    TEXT,
    created_at        TIMESTAMPTZ   NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ   NOT NULL DEFAULT now()
);

COMMENT ON TABLE  capture_sessions                IS 'One row per measurement capture attempt by a user.';
COMMENT ON COLUMN capture_sessions.status         IS 'Lifecycle state: empty → processing → success | failed.';
COMMENT ON COLUMN capture_sessions.is_active      IS 'True for the single most-recent successful session per user.';
COMMENT ON COLUMN capture_sessions.retry_count    IS 'Number of photo re-uploads after a failed state.';
COMMENT ON COLUMN capture_sessions.entered_stature IS 'User-provided height in centimetres (100–250).';

-- Automatically update updated_at on every row change
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_capture_sessions_updated_at
    BEFORE UPDATE ON capture_sessions
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Enforces AC-01.3: only one active session per user at any time.
-- Deactivating old sessions before setting a new one keeps this index valid.
CREATE UNIQUE INDEX uix_one_active_per_user
    ON capture_sessions (user_id)
    WHERE is_active = TRUE;

-- Row Level Security: users can only see and modify their own sessions (NFR-04)
ALTER TABLE capture_sessions ENABLE ROW LEVEL SECURITY;

CREATE POLICY sessions_select_owner ON capture_sessions
    FOR SELECT USING (user_id = auth.uid());

CREATE POLICY sessions_insert_owner ON capture_sessions
    FOR INSERT WITH CHECK (user_id = auth.uid());

CREATE POLICY sessions_update_owner ON capture_sessions
    FOR UPDATE USING (user_id = auth.uid());
