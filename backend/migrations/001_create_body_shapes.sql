-- Migration 001 — Create body_shapes reference table
-- Module 2 — Photo Capture & Measurement Estimation
-- Task T-01.1 — AC-08.1, Design §3.3

CREATE TABLE body_shapes (
    code        VARCHAR(30)  PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,
    description TEXT
);

COMMENT ON TABLE body_shapes IS 'Reference table for the five body silhouette classifications.';

-- Seed the five silhouette types with their ratio rules
INSERT INTO body_shapes (code, name, description) VALUES
    ('HOURGLASS',          'Sablier (X)',           'Waist/Bust ≤ 0.75 AND Waist/Hips ≤ 0.75 AND |Bust−Hips| ≤ 5 cm'),
    ('PEAR',               'Poire (A)',             'Hips > Bust + 5 cm AND Waist < Hips'),
    ('INVERTED_TRIANGLE',  'Triangle inversé (V)',  'Bust > Hips + 5 cm'),
    ('APPLE',              'Pomme (O)',             'Waist ≥ Bust OR Waist ≥ Hips'),
    ('RECTANGLE',          'Rectangle (H)',         'Subtle waist definition; none of the above');
