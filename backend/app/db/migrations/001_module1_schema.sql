-- Module 1: Authentication & User Profile
-- Migration: 001_module1_schema
-- Run against your Supabase PostgreSQL instance via the Supabase SQL Editor or psql.

-- ── Role enum ───────────────────────────────────────────────────────────────
CREATE TYPE user_role AS ENUM ('Client', 'Tailor', 'Admin');

-- ── Users ───────────────────────────────────────────────────────────────────
CREATE TABLE users (
    cni                VARCHAR(9)    PRIMARY KEY
                                     CHECK (cni ~ '^[A-Za-z0-9]{9}$'),
    nom                VARCHAR(100)  NOT NULL,
    email              VARCHAR(255)  NOT NULL UNIQUE,
    mot_de_passe       TEXT          NOT NULL,        -- bcrypt hash only
    role               user_role     NOT NULL,
    is_active          BOOLEAN       NOT NULL DEFAULT TRUE,
    date_inscription   TIMESTAMPTZ   NOT NULL DEFAULT (timezone('utc', now()))
);

CREATE INDEX idx_users_email     ON users (email);
CREATE INDEX idx_users_role      ON users (role);
CREATE INDEX idx_users_is_active ON users (is_active);

-- ── Profile photos ──────────────────────────────────────────────────────────
CREATE TABLE photo_profil (
    id_photo     UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
    cni          VARCHAR(9)    NOT NULL REFERENCES users (cni) ON DELETE CASCADE,
    url_photo    TEXT          NOT NULL,
    date_upload  TIMESTAMPTZ   NOT NULL DEFAULT (timezone('utc', now()))
);

CREATE INDEX idx_photo_profil_cni ON photo_profil (cni);

-- ── Body measurements ────────────────────────────────────────────────────────
CREATE TABLE mensuration (
    id_mesure          UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
    cni                VARCHAR(9)    NOT NULL REFERENCES users (cni) ON DELETE CASCADE,
    tour_poitrine      NUMERIC(6,2)  NOT NULL CHECK (tour_poitrine  > 0 AND tour_poitrine  <= 300),
    tour_taille        NUMERIC(6,2)  NOT NULL CHECK (tour_taille    > 0 AND tour_taille    <= 300),
    tour_hanches       NUMERIC(6,2)  NOT NULL CHECK (tour_hanches   > 0 AND tour_hanches   <= 300),
    longueur_bras      NUMERIC(6,2)  NOT NULL CHECK (longueur_bras  > 0 AND longueur_bras  <= 300),
    hauteur            NUMERIC(6,2)  NOT NULL CHECK (hauteur        > 0 AND hauteur        <= 300),
    date_mensuration   TIMESTAMPTZ   NOT NULL DEFAULT (timezone('utc', now())),
    source_event_hash  TEXT          UNIQUE    -- SHA-256 of (cni||values||source_timestamp)
                                               -- NULL for manual entries; set for event-driven entries
);

CREATE INDEX idx_mensuration_cni       ON mensuration (cni);
CREATE INDEX idx_mensuration_date      ON mensuration (cni, date_mensuration DESC);
CREATE INDEX idx_mensuration_evt_hash  ON mensuration (source_event_hash)
                                        WHERE source_event_hash IS NOT NULL;

-- ── Report archive ───────────────────────────────────────────────────────────
CREATE TABLE rapport_archive (
    id               UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
    cni              VARCHAR(9)    NOT NULL REFERENCES users (cni) ON DELETE CASCADE,
    report_id        TEXT          NOT NULL,
    date_generation  TIMESTAMPTZ   NOT NULL,
    archived_at      TIMESTAMPTZ   NOT NULL DEFAULT (timezone('utc', now())),
    UNIQUE (cni, report_id)                   -- idempotency: one archive row per (user, report)
);

CREATE INDEX idx_rapport_cni ON rapport_archive (cni, archived_at DESC);

-- ── JWT denylist (logout invalidation) ──────────────────────────────────────
CREATE TABLE token_denylist (
    jti         TEXT          PRIMARY KEY,   -- JWT ID claim (UUID)
    expires_at  TIMESTAMPTZ   NOT NULL       -- used by cleanup job to purge expired rows
);

CREATE INDEX idx_token_denylist_expires ON token_denylist (expires_at);

-- ── Tailor ↔ Client assignment (Tailor RBAC) ────────────────────────────────
CREATE TABLE tailor_client_assignment (
    tailor_cni  VARCHAR(9)  NOT NULL REFERENCES users (cni) ON DELETE CASCADE,
    client_cni  VARCHAR(9)  NOT NULL REFERENCES users (cni) ON DELETE CASCADE,
    assigned_at TIMESTAMPTZ NOT NULL DEFAULT (timezone('utc', now())),
    PRIMARY KEY (tailor_cni, client_cni)
);

CREATE INDEX idx_tca_tailor ON tailor_client_assignment (tailor_cni);
CREATE INDEX idx_tca_client ON tailor_client_assignment (client_cni);
