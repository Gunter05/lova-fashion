#!/usr/bin/env python3
"""
init_db.py — Exécute toutes les migrations SQL sur la base Supabase.

Usage
-----
    cd backend
    python scripts/init_db.py

Prérequis
---------
    - DATABASE_URL défini dans backend/.env  (format postgresql://...)
    - psycopg2-binary installé  (pip install psycopg2-binary)

Ordre d'exécution
-----------------
    1. app/db/migrations/001_module1_schema.sql          → Module 1  (users, auth)
    2. app/modules/auth_catalogues/migrations/001_...    → Module 3  (fabric_categories, fabrics)
    3. app/modules/auth_catalogues/migrations/002_...    → Module 4  (models, zones, snapshots)
    4. backend/migrations/001_create_body_shapes.sql     → Module 2  (body_shapes)
    5. backend/migrations/002_create_capture_sessions.sql
    6. backend/migrations/003_create_raw_measurements.sql
    7. backend/migrations/004_storage_bucket_rls.sql
    8. backend/migrations/005_create_ease_rules.sql      → Module 5  (ease_rules)
    9. backend/migrations/006_create_measurement_adjustments.sql

Chaque fichier est exécuté dans sa propre transaction.
Si un fichier échoue, le script s'arrête et affiche l'erreur.
Les migrations sont idempotentes (IF NOT EXISTS) — sûr de relancer.
"""

import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Résolution du chemin racine backend/
# ---------------------------------------------------------------------------

BACKEND_DIR = Path(__file__).resolve().parent.parent  # backend/

# Charger .env
env_file = BACKEND_DIR / ".env"
if env_file.exists():
    from dotenv import load_dotenv
    load_dotenv(env_file)
    print(f"✓ .env chargé depuis {env_file}")
else:
    print(f"⚠  Aucun fichier .env trouvé dans {BACKEND_DIR}")

DATABASE_URL: str = os.environ.get("DATABASE_URL", "")

if not DATABASE_URL:
    print("ERREUR : DATABASE_URL n'est pas défini.", file=sys.stderr)
    print("  Ajoutez DATABASE_URL=postgresql://... dans backend/.env", file=sys.stderr)
    sys.exit(1)

# Normaliser l'URL pour psycopg2 (supprimer le préfixe asyncpg si présent)
if DATABASE_URL.startswith("postgresql+asyncpg://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://", 1)

# ---------------------------------------------------------------------------
# Ordre des migrations
# ---------------------------------------------------------------------------

MIGRATIONS: list[Path] = [
    # Module 1 — Auth & User Profile
    BACKEND_DIR / "app" / "db" / "migrations" / "001_module1_schema.sql",
    # Module 3 — Fabric Catalog
    BACKEND_DIR / "app" / "modules" / "auth_catalogues" / "migrations" / "001_create_fabric_tables.sql",
    # Module 4 — Pattern Catalog
    BACKEND_DIR / "app" / "modules" / "auth_catalogues" / "migrations" / "002_create_model_tables.sql",
    # Module 2 — Measurements (body shapes, capture sessions, raw measurements, storage RLS)
    BACKEND_DIR / "migrations" / "001_create_body_shapes.sql",
    BACKEND_DIR / "migrations" / "002_create_capture_sessions.sql",
    BACKEND_DIR / "migrations" / "003_create_raw_measurements.sql",
    BACKEND_DIR / "migrations" / "004_storage_bucket_rls.sql",
    # Module 5 — Ease Allowance Engine
    BACKEND_DIR / "migrations" / "005_create_ease_rules.sql",
    BACKEND_DIR / "migrations" / "006_create_measurement_adjustments.sql",
]


def run_migrations() -> None:
    try:
        import psycopg2
    except ImportError:
        print(
            "ERREUR : psycopg2-binary n'est pas installé.\n"
            "  Exécutez : pip install psycopg2-binary",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"\nConnexion à la base de données…")
    try:
        conn = psycopg2.connect(DATABASE_URL)
    except Exception as exc:
        print(f"ERREUR de connexion : {exc}", file=sys.stderr)
        sys.exit(1)

    conn.autocommit = False
    print("✓ Connecté.\n")

    total = len(MIGRATIONS)
    for i, path in enumerate(MIGRATIONS, start=1):
        label = path.relative_to(BACKEND_DIR)
        if not path.exists():
            print(f"  [{i}/{total}] ⚠  IGNORÉ (fichier introuvable) : {label}")
            continue

        sql = path.read_text(encoding="utf-8")
        print(f"  [{i}/{total}] Exécution de {label}…", end=" ")

        try:
            with conn.cursor() as cur:
                cur.execute(sql)
            conn.commit()
            print("✓")
        except Exception as exc:
            conn.rollback()
            print(f"\n\nERREUR dans {label}:\n  {exc}", file=sys.stderr)
            conn.close()
            sys.exit(1)

    conn.close()
    print(f"\n✓ {total} migration(s) appliquée(s) avec succès.")


if __name__ == "__main__":
    run_migrations()
