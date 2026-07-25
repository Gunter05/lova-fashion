-- ============================================================================
-- Migration 007 — Module 7: Final Result & Report (Synthesis)
-- Creates the `rapport_mesure` table with RLS for immutable report storage.
-- ============================================================================

-- ── rapport_mesure table ─────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS rapport_mesure (
    id_report             UUID          PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Foreign keys to upstream entities (RESTRICT prevents orphaned reports)
    cni                   VARCHAR(9)    NOT NULL
                          REFERENCES users(cni)                      ON DELETE RESTRICT,
    adjustment_id         UUID          NOT NULL
                          REFERENCES measurement_adjustments(id)     ON DELETE RESTRICT,
    fabric_id             UUID          NOT NULL
                          REFERENCES fabrics(fabric_id)              ON DELETE RESTRICT,
    model_id              UUID          NOT NULL
                          REFERENCES models(model_id)                ON DELETE RESTRICT,

    -- Verdict (immutable, validated at application layer before insert)
    verdict               VARCHAR(30)   NOT NULL
                          CHECK (verdict IN ('compatible', 'incompatible', 'minor_adjustments')),

    -- Immutable JSONB snapshot of Module 5 adjusted measurements at generation time
    -- Schema: {adjusted_bust_cm, adjusted_waist_cm, adjusted_hips_cm,
    --          bust_ease_cm, waist_ease_cm, hips_ease_cm, ease_source}
    adjusted_measurements JSONB         NOT NULL,

    -- Textual recommendation from Module 6
    advice                TEXT          NOT NULL,

    -- Incompatibility detail — NULL unless verdict = 'incompatible'
    -- Schema: [{zone: str, reason: str}, ...]
    incompatible_zones    JSONB         NULL,

    -- Generation timestamp — always set server-side (NFR-06)
    generated_at          TIMESTAMPTZ   NOT NULL DEFAULT (timezone('utc', now()))
);

COMMENT ON TABLE rapport_mesure IS
    'Immutable synthesis records linking one Measurement, one Fabric, and one Garment Model. '
    'Created exclusively via the compatibility.evaluated EventBus event. '
    'No UPDATE or DELETE operations are permitted (Module 7 is sole writer).';

-- ── Indexes ───────────────────────────────────────────────────────────────────

-- Efficient client history queries (Req 6 AC1)
CREATE INDEX IF NOT EXISTS idx_rapport_mesure_cni_generated
    ON rapport_mesure (cni, generated_at DESC);

-- ── Row-Level Security ────────────────────────────────────────────────────────
-- SELECT policy scoped to the current user's CNI (set by Module 1 middleware).
-- No UPDATE or DELETE policies — immutability enforced at DB level (NFR-03).

ALTER TABLE rapport_mesure ENABLE ROW LEVEL SECURITY;

CREATE POLICY rapport_select_owner ON rapport_mesure
    FOR SELECT
    USING (cni = current_setting('app.current_user_cni', true));

-- Admins and tailors query through the application layer which bypasses RLS
-- by using service_role credentials; client-facing reads use this policy.
