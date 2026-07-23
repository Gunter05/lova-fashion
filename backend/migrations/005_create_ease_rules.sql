-- Migration 005 — Create ease_rules reference table
-- Module 5 — Ease Allowance Calculation Engine
-- Task T-01.1 — AC-02.1, AC-02.2, AC-02.3, NFR-06, Design §3.1

CREATE TABLE ease_rules (
    elasticity_category  VARCHAR(30)   PRIMARY KEY,
    ease_delta_cm        DECIMAL(4,1)  NOT NULL,
    description          TEXT
);

COMMENT ON TABLE ease_rules IS
    'Reference table mapping fabric elasticity categories to ease delta values in cm.
     Read-only at runtime; modified only via migrations (NFR-06).';

-- Seed the three canonical ease rules (AC-02.1, AC-02.2, AC-02.3)
INSERT INTO ease_rules (elasticity_category, ease_delta_cm, description) VALUES
    ('rigid',        4.0,  'Tissu non-élastique (ex. Pagne Wax) — aisance +4 cm'),
    ('semi-stretch', 2.0,  'Tissu légèrement élastique — aisance +2 cm'),
    ('stretch',     -2.0,  'Tissu très élastique (ex. Jersey) — aisance −2 cm');
