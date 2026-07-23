-- Migration 003 — Create raw_measurements table
-- Module 2 — Photo Capture & Measurement Estimation
-- Task T-01.3 — AC-08.2, NFR-04, Design §3.2

CREATE TABLE raw_measurements (
    id               UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id       UUID         NOT NULL UNIQUE REFERENCES capture_sessions(id) ON DELETE CASCADE,
    bust_cm          DECIMAL(5,1) NOT NULL,
    waist_cm         DECIMAL(5,1) NOT NULL,
    hips_cm          DECIMAL(5,1) NOT NULL,
    silhouette_code  VARCHAR(30)  NOT NULL REFERENCES body_shapes(code),
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT now()
);

COMMENT ON TABLE  raw_measurements                 IS 'Anatomical measurements produced by the CV pipeline for a capture session.';
COMMENT ON COLUMN raw_measurements.bust_cm         IS 'Estimated bust circumference in cm, DECIMAL(5,1).';
COMMENT ON COLUMN raw_measurements.waist_cm        IS 'Estimated waist circumference in cm, DECIMAL(5,1).';
COMMENT ON COLUMN raw_measurements.hips_cm         IS 'Estimated hip circumference in cm, DECIMAL(5,1).';
COMMENT ON COLUMN raw_measurements.silhouette_code IS 'FK to body_shapes.code — one of HOURGLASS, PEAR, INVERTED_TRIANGLE, APPLE, RECTANGLE.';

-- Row Level Security: expose measurements only to their session owner (NFR-04)
ALTER TABLE raw_measurements ENABLE ROW LEVEL SECURITY;

CREATE POLICY measurements_select_owner ON raw_measurements
    FOR SELECT USING (
        session_id IN (
            SELECT id FROM capture_sessions WHERE user_id = auth.uid()
        )
    );

CREATE POLICY measurements_insert_owner ON raw_measurements
    FOR INSERT WITH CHECK (
        session_id IN (
            SELECT id FROM capture_sessions WHERE user_id = auth.uid()
        )
    );
