-- =============================================================================
-- Migration 001: Create fabric_categories and fabrics tables
-- Module: Fabric Catalog (Module 3)
-- =============================================================================

-- Enable the pgcrypto extension for gen_random_uuid() if not already enabled.
-- On Supabase this extension is available by default; the CREATE EXTENSION
-- statement is idempotent (IF NOT EXISTS) so it is safe to run every time.
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ---------------------------------------------------------------------------
-- Table: fabric_categories
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS fabric_categories (
    category_id              UUID          NOT NULL DEFAULT gen_random_uuid(),
    category_name            VARCHAR(50)   NOT NULL,
    category_description     TEXT,
    reference_rigidity_level VARCHAR(12)   NOT NULL,
    created_at               TIMESTAMPTZ   NOT NULL DEFAULT now(),
    updated_at               TIMESTAMPTZ   NOT NULL DEFAULT now(),

    CONSTRAINT pk_fabric_categories
        PRIMARY KEY (category_id),

    CONSTRAINT chk_fabric_categories_rigidity_level
        CHECK (reference_rigidity_level IN ('rigid', 'semi-stretch', 'stretch'))
);

-- ---------------------------------------------------------------------------
-- Table: fabrics
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS fabrics (
    fabric_id             UUID           NOT NULL DEFAULT gen_random_uuid(),
    fabric_name           VARCHAR(100)   NOT NULL,
    fabric_elasticity_rate NUMERIC(5, 2) NOT NULL,
    fabric_weight         NUMERIC(8, 2)  NOT NULL,
    fabric_composition    TEXT,
    fabric_unit_price     NUMERIC(10, 2) NOT NULL,
    fabric_photo          TEXT,
    fabric_status         VARCHAR(11)    NOT NULL DEFAULT 'available',
    category_id           UUID           NOT NULL,
    created_at            TIMESTAMPTZ    NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ    NOT NULL DEFAULT now(),

    CONSTRAINT pk_fabrics
        PRIMARY KEY (fabric_id),

    CONSTRAINT fk_fabrics_category
        FOREIGN KEY (category_id)
        REFERENCES fabric_categories (category_id),

    CONSTRAINT chk_fabrics_elasticity_rate
        CHECK (fabric_elasticity_rate >= 0 AND fabric_elasticity_rate <= 100),

    CONSTRAINT chk_fabrics_weight
        CHECK (fabric_weight > 0),

    CONSTRAINT chk_fabrics_unit_price
        CHECK (fabric_unit_price > 0),

    CONSTRAINT chk_fabrics_status
        CHECK (fabric_status IN ('available', 'unavailable', 'archived'))
);

-- ---------------------------------------------------------------------------
-- Indexes
-- ---------------------------------------------------------------------------

-- Supports filtering fabrics by category (used in list_available_fabrics)
CREATE INDEX IF NOT EXISTS idx_fabrics_category_id
    ON fabrics (category_id);

-- Supports filtering fabrics by status (used in listing and selection logic)
CREATE INDEX IF NOT EXISTS idx_fabrics_status
    ON fabrics (fabric_status);
