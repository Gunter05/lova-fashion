-- Migration 006 — Create measurement_adjustments table
-- Module 5 — Ease Allowance Calculation Engine
-- Task T-01.2 — AC-01.6, AC-03.1, AC-03.2, NFR-03, NFR-04, Design §3.2

CREATE TABLE measurement_adjustments (
    id                  UUID          PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Upstream references (Module 2 session, Module 3 fabric)
    session_id          UUID          NOT NULL
                        REFERENCES capture_sessions(id) ON DELETE CASCADE,
    fabric_id           UUID          NOT NULL,   -- logical FK to fabrics table (Module 3)

    -- Raw input snapshot (AC-03.2 — both raw and adjusted stored for auditability)
    raw_bust_cm         DECIMAL(5,1)  NOT NULL,
    raw_waist_cm        DECIMAL(5,1)  NOT NULL,
    raw_hips_cm         DECIMAL(5,1)  NOT NULL,

    -- Per-zone ease applied (AC-03.1 — stored independently per zone)
    bust_ease_cm        DECIMAL(4,1)  NOT NULL,
    waist_ease_cm       DECIMAL(4,1)  NOT NULL,
    hips_ease_cm        DECIMAL(4,1)  NOT NULL,

    -- Adjusted output values (NFR-04 — DECIMAL(5,1), one decimal place)
    adjusted_bust_cm    DECIMAL(5,1)  NOT NULL,
    adjusted_waist_cm   DECIMAL(5,1)  NOT NULL,
    adjusted_hips_cm    DECIMAL(5,1)  NOT NULL,

    -- Metadata
    ease_source         VARCHAR(30)   NOT NULL DEFAULT 'rule'
                        CHECK (ease_source IN ('rule', 'default_fallback')),
    calculated_at       TIMESTAMPTZ   NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ   NOT NULL DEFAULT now(),

    -- One adjustment per (session, fabric) pair — supports upsert (AC-01.6)
    CONSTRAINT uq_adjustment_session_fabric UNIQUE (session_id, fabric_id)
);

COMMENT ON TABLE  measurement_adjustments                IS 'Ease-adjusted garment cutting measurements per (session, fabric) pair.';
COMMENT ON COLUMN measurement_adjustments.ease_source    IS '''rule'' = delta from ease_rules table; ''default_fallback'' = unknown elasticity category, +3 cm applied.';
COMMENT ON COLUMN measurement_adjustments.bust_ease_cm   IS 'Ease delta actually applied to the bust zone (cm). Stored per zone for future per-zone override support.';
COMMENT ON COLUMN measurement_adjustments.waist_ease_cm  IS 'Ease delta actually applied to the waist zone (cm).';
COMMENT ON COLUMN measurement_adjustments.hips_ease_cm   IS 'Ease delta actually applied to the hips zone (cm).';

-- Auto-update updated_at on every row change.
-- Reuses set_updated_at() created by Migration 002 (Module 2).
CREATE TRIGGER trg_measurement_adjustments_updated_at
    BEFORE UPDATE ON measurement_adjustments
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Row Level Security: users can only read/write adjustments on their own sessions (NFR-03)
ALTER TABLE measurement_adjustments ENABLE ROW LEVEL SECURITY;

CREATE POLICY adjustments_select_owner ON measurement_adjustments
    FOR SELECT USING (
        session_id IN (
            SELECT id FROM capture_sessions WHERE user_id = auth.uid()
        )
    );

CREATE POLICY adjustments_insert_owner ON measurement_adjustments
    FOR INSERT WITH CHECK (
        session_id IN (
            SELECT id FROM capture_sessions WHERE user_id = auth.uid()
        )
    );

CREATE POLICY adjustments_update_owner ON measurement_adjustments
    FOR UPDATE USING (
        session_id IN (
            SELECT id FROM capture_sessions WHERE user_id = auth.uid()
        )
    );
