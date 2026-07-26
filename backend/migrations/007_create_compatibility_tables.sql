-- Migration 007 — Create Module 6 compatibility tables
-- Module 6 — Fabric/Model/Silhouette Compatibility Engine
-- Requirements: 2.1, 7.1–7.7, 9.1, 13.3

-- ─────────────────────────────────────────────────────────────────────────────
-- 1. compatibility_rules — admin-configured rule thresholds (Req 2.1, 9.1)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE compatibility_rules (
    rule_id               UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
    cut_type              VARCHAR(30)   NOT NULL,
    fabric_property       VARCHAR(30)   NOT NULL,
    zone_id               UUID          REFERENCES critical_zone(zone_id),   -- nullable, logical scope
    mathematical_condition VARCHAR(200) NOT NULL,
    severity_level        VARCHAR(20)   NOT NULL
                          CHECK (severity_level IN ('Incompatible', 'Reserve')),
    explanation_message   TEXT
                          CHECK (char_length(explanation_message) <= 500),
    is_active             BOOLEAN       NOT NULL DEFAULT TRUE,
    version               INTEGER       NOT NULL DEFAULT 1,
    admin_id              UUID          NOT NULL,   -- logical FK to auth.users
    created_at            TIMESTAMPTZ   NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ   NOT NULL DEFAULT now()
);

COMMENT ON TABLE  compatibility_rules                      IS 'Admin-configurable rule set. No hard-coded thresholds in application code.';
COMMENT ON COLUMN compatibility_rules.zone_id              IS 'Nullable — rule applies to a specific critical zone when set, or globally when NULL.';
COMMENT ON COLUMN compatibility_rules.mathematical_condition IS 'Short expression (≤ 200 chars) evaluated server-side via simpleeval; variable: value (adjusted cm).';
COMMENT ON COLUMN compatibility_rules.severity_level       IS '"Incompatible" = hard block; "Reserve" = soft warning.';
COMMENT ON COLUMN compatibility_rules.version              IS 'Incremented on every PATCH; used for rule-version deduplication and audit immutability.';
COMMENT ON COLUMN compatibility_rules.admin_id             IS 'UUID of the admin who created/last modified this rule (logical FK to auth.users).';

-- Compound index for the version-deduped rule-loading query (Req 9.1, Design §Rule Version Deduplication)
CREATE INDEX idx_rules_cut_fabric_active
    ON compatibility_rules (cut_type, fabric_property, is_active);

-- ─────────────────────────────────────────────────────────────────────────────
-- 2. model_morphology — body-shape suitability association (MODULE_MORPHOLOGY_LINK)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE model_morphology (
    model_id          UUID        NOT NULL REFERENCES model(model_id) ON DELETE CASCADE,
    morphology_id     UUID        NOT NULL,   -- logical FK to body_shapes
    suitability_score VARCHAR(15) NOT NULL
                      CHECK (suitability_score IN ('Ideal', 'Flattering', 'Avoid')),
    PRIMARY KEY (model_id, morphology_id)
);

COMMENT ON TABLE  model_morphology                   IS 'Suitability of a garment model for a given body morphology (MODULE_MORPHOLOGY_LINK).';
COMMENT ON COLUMN model_morphology.morphology_id     IS 'Logical FK to body_shapes.id — no hard FK to keep body_shapes decoupled.';
COMMENT ON COLUMN model_morphology.suitability_score IS '"Ideal" = best fit; "Flattering" = acceptable; "Avoid" = generates a Reserve risk zone.';

-- ─────────────────────────────────────────────────────────────────────────────
-- 3. verdict_evaluations — persisted evaluation records (Req 7.1–7.7)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE verdict_evaluations (
    evaluation_id       UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    global_status       VARCHAR(40) NOT NULL
                        CHECK (global_status IN (
                            'Compatible',
                            'Compatible_with_Reservations',
                            'Incompatible',
                            'Indeterminate',
                            'Failed'
                        )),
    missing_data_log    TEXT,                           -- nullable; populated on Indeterminate/Failed
    fabric_recommendation VARCHAR(50),                  -- nullable; optional admin note
    client_id           UUID        NOT NULL,           -- logical FK to auth.users
    model_id            UUID        NOT NULL REFERENCES model(model_id),
    fabric_id           UUID        NOT NULL,           -- logical FK to fabrics
    measurements_id     UUID        NOT NULL REFERENCES measurement_adjustments(id),
    morphology_id       UUID        NOT NULL            -- logical FK to body_shapes
);

COMMENT ON TABLE  verdict_evaluations                     IS 'One row per compatibility check run; immutable after INSERT (audit trail).';
COMMENT ON COLUMN verdict_evaluations.global_status       IS 'Aggregate verdict over all evaluated zones.';
COMMENT ON COLUMN verdict_evaluations.missing_data_log    IS 'Populated only when global_status is Indeterminate or Failed — describes what data was absent or which error occurred.';
COMMENT ON COLUMN verdict_evaluations.client_id           IS 'End-user who triggered the evaluation (logical FK to auth.users).';
COMMENT ON COLUMN verdict_evaluations.fabric_id           IS 'Logical FK to fabrics — no hard FK to keep modules decoupled.';
COMMENT ON COLUMN verdict_evaluations.morphology_id       IS 'Logical FK to body_shapes — no hard FK to keep modules decoupled.';

-- Index for owner-scoped listing queries (Req 13.3, Design §API)
CREATE INDEX idx_verdict_client
    ON verdict_evaluations (client_id, created_at DESC);

-- ─────────────────────────────────────────────────────────────────────────────
-- 4. risk_zones — per-zone rule-firing detail rows (Req 7.1–7.7)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE risk_zones (
    risk_id             UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
    evaluation_id       UUID          NOT NULL
                        REFERENCES verdict_evaluations(evaluation_id) ON DELETE CASCADE,
    rule_id             UUID          REFERENCES compatibility_rules(rule_id),   -- nullable (morphology/fabric checks)
    zone_id             UUID          REFERENCES critical_zone(zone_id),         -- nullable (global rules)
    calculated_variance NUMERIC(8,4)  NOT NULL,
    localized_verdict   VARCHAR(20)   NOT NULL
                        CHECK (localized_verdict IN ('Incompatible', 'Reserve')),
    explanation         TEXT          NOT NULL,
    rule_version        INTEGER       NOT NULL
);

COMMENT ON TABLE  risk_zones                      IS 'One row per fired rule per evaluation; immutable after INSERT (audit trail).';
COMMENT ON COLUMN risk_zones.rule_id              IS 'Nullable — NULL for synthetic risk zones created by morphology or fabric-link checks.';
COMMENT ON COLUMN risk_zones.zone_id              IS 'Nullable — NULL when the originating rule applies globally (zone_id IS NULL on the rule).';
COMMENT ON COLUMN risk_zones.calculated_variance  IS 'Numeric value of the bound variable (adjusted_cm) at evaluation time.';
COMMENT ON COLUMN risk_zones.rule_version         IS 'Snapshot of compatibility_rules.version at evaluation time — ensures immutability of past evaluations (Req 7.4).';

-- ─────────────────────────────────────────────────────────────────────────────
-- 5. updated_at auto-trigger for compatibility_rules (Req 9.1)
--    CREATE OR REPLACE ensures idempotency if set_updated_at() was already
--    defined by Migration 002.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_compatibility_rules_updated_at
    BEFORE UPDATE ON compatibility_rules
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ─────────────────────────────────────────────────────────────────────────────
-- 6. Row Level Security (Req 13.3)
-- ─────────────────────────────────────────────────────────────────────────────

-- verdict_evaluations: owner can read their own evaluations
ALTER TABLE verdict_evaluations ENABLE ROW LEVEL SECURITY;

CREATE POLICY verdict_evaluations_select_owner ON verdict_evaluations
    FOR SELECT USING (client_id = auth.uid());

-- risk_zones: owner can read risk zones belonging to their own evaluations
ALTER TABLE risk_zones ENABLE ROW LEVEL SECURITY;

CREATE POLICY risk_zones_select_owner ON risk_zones
    FOR SELECT USING (
        evaluation_id IN (
            SELECT evaluation_id
            FROM verdict_evaluations
            WHERE client_id = auth.uid()
        )
    );
