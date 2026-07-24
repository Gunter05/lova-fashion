-- =============================================================================
-- Migration 002: Create model catalog tables
-- Module: Pattern Catalog (Module 4)
-- Date: 2025-07-14
-- =============================================================================
--
-- Tables created (in dependency order):
--   1. critical_zone         — reference/seed table for body measurement zones
--   2. model                 — garment pattern master record
--   3. model_critical_zone   — join: model ↔ critical_zone (composite PK)
--   4. model_fabric          — join: model ↔ fabric (composite PK, no FK to Module 3)
--   5. model_snapshot        — immutable audit/history of published model edits
-- =============================================================================

BEGIN;

-- Enable the pgcrypto extension for gen_random_uuid() if not already enabled.
-- On Supabase this extension is available by default; the CREATE EXTENSION
-- statement is idempotent (IF NOT EXISTS) so it is safe to run every time.
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ---------------------------------------------------------------------------
-- Table: critical_zone
-- Reference table — rows are fixed seed data; not edited by users.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS critical_zone (
    zone_id     UUID        NOT NULL DEFAULT gen_random_uuid(),
    zone_name   VARCHAR(50) NOT NULL,
    description TEXT,

    CONSTRAINT pk_critical_zone
        PRIMARY KEY (zone_id),

    CONSTRAINT uq_critical_zone_name
        UNIQUE (zone_name)
);

-- Seed rows (idempotent via ON CONFLICT DO NOTHING)
INSERT INTO critical_zone (zone_name, description) VALUES
    ('Chest',     'Circumference around the fullest part of the chest'),
    ('Waist',     'Circumference at the natural waistline'),
    ('Hips',      'Circumference around the fullest part of the hips'),
    ('Shoulders', 'Width across the shoulders'),
    ('Neck',      'Circumference at the base of the neck'),
    ('Thighs',    'Circumference around the fullest part of the thigh'),
    ('Ankles',    'Circumference around the ankle')
ON CONFLICT (zone_name) DO NOTHING;

-- ---------------------------------------------------------------------------
-- Table: model
-- Master record for a garment pattern.
-- creator_id references auth.users managed by Supabase (Module 1).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS model (
    model_id      UUID         NOT NULL DEFAULT gen_random_uuid(),
    model_name    VARCHAR(100) NOT NULL,
    description   TEXT,
    photo_url     VARCHAR(255) NOT NULL,
    garment_type  VARCHAR(50)  NOT NULL,
    cut_type      VARCHAR(20)  NOT NULL,
    status        VARCHAR(20)  NOT NULL DEFAULT 'Draft',
    version       INT          NOT NULL DEFAULT 1,
    creator_id    UUID         NOT NULL,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),

    CONSTRAINT pk_model
        PRIMARY KEY (model_id),

    CONSTRAINT fk_model_creator
        FOREIGN KEY (creator_id)
        REFERENCES auth.users (id),

    CONSTRAINT chk_model_garment_type
        CHECK (garment_type IN (
            'Dress', 'Shirt', 'Blouse', 'Trousers', 'Skirt',
            'Jacket', 'Coat', 'Shorts', 'Suit', 'Traditional'
        )),

    CONSTRAINT chk_model_cut_type
        CHECK (cut_type IN ('Fitted', 'Semi-fitted', 'Loose')),

    CONSTRAINT chk_model_status
        CHECK (status IN ('Draft', 'Published', 'Archived'))
);

-- ---------------------------------------------------------------------------
-- Table: model_critical_zone
-- Join table — many-to-many between model and critical_zone.
-- Cascade delete: removing a model removes its zone assignments.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS model_critical_zone (
    model_id UUID NOT NULL,
    zone_id  UUID NOT NULL,

    CONSTRAINT pk_model_critical_zone
        PRIMARY KEY (model_id, zone_id),

    CONSTRAINT fk_mcz_model
        FOREIGN KEY (model_id)
        REFERENCES model (model_id)
        ON DELETE CASCADE,

    CONSTRAINT fk_mcz_zone
        FOREIGN KEY (zone_id)
        REFERENCES critical_zone (zone_id)
);

-- ---------------------------------------------------------------------------
-- Table: model_fabric
-- Join table — many-to-many between model and fabric (Module 3).
-- fabric_id has NO DB-level foreign key: modules are loosely coupled;
-- referential integrity is enforced at the service layer during assignment.
-- Cascade delete: removing a model removes its fabric assignments.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS model_fabric (
    model_id  UUID NOT NULL,
    fabric_id UUID NOT NULL,

    CONSTRAINT pk_model_fabric
        PRIMARY KEY (model_id, fabric_id),

    CONSTRAINT fk_mf_model
        FOREIGN KEY (model_id)
        REFERENCES model (model_id)
        ON DELETE CASCADE
);

-- ---------------------------------------------------------------------------
-- Table: model_snapshot
-- Immutable audit/history record written before each edit of a Published model.
-- model_id has NO DB-level foreign key to allow historical snapshots to persist
-- even if the live model row is ever removed.
-- zones and fabrics are embedded as JSONB so the snapshot is self-contained.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS model_snapshot (
    snapshot_id      UUID         NOT NULL DEFAULT gen_random_uuid(),
    model_id         UUID         NOT NULL,
    snapshot_version INT          NOT NULL,
    model_name       VARCHAR(100) NOT NULL,
    description      TEXT,
    garment_type     VARCHAR(50)  NOT NULL,
    cut_type         VARCHAR(20)  NOT NULL,
    photo_url        VARCHAR(255) NOT NULL,
    status           VARCHAR(20)  NOT NULL,
    creator_id       UUID         NOT NULL,
    zones            JSONB        NOT NULL,  -- [{zone_id, zone_name}, ...]
    fabrics          JSONB        NOT NULL,  -- [{fabric_id, fabric_name}, ...]
    snapshotted_at   TIMESTAMPTZ  NOT NULL DEFAULT now(),

    CONSTRAINT pk_model_snapshot
        PRIMARY KEY (snapshot_id),

    CONSTRAINT uq_model_snapshot_version
        UNIQUE (model_id, snapshot_version)
);

-- ---------------------------------------------------------------------------
-- Indexes
-- ---------------------------------------------------------------------------

-- Supports filtering models by status (Draft/Published/Archived listing)
CREATE INDEX IF NOT EXISTS idx_model_status
    ON model (status);

-- Supports filtering models by garment_type (catalog browse)
CREATE INDEX IF NOT EXISTS idx_model_garment_type
    ON model (garment_type);

-- Supports looking up all snapshots for a given model (audit history)
CREATE INDEX IF NOT EXISTS idx_model_snapshot_model_id
    ON model_snapshot (model_id);

COMMIT;
