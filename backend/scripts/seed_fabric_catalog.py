#!/usr/bin/env python3
"""
seed_fabric_catalog.py — Insère les catégories et tissus réels dans la base
                          et uploade leurs photos vers Supabase Storage.

Usage
-----
    cd backend
    python scripts/seed_fabric_catalog.py

    # Pour réinitialiser (supprimer les données existantes avant de re-seeder)
    python scripts/seed_fabric_catalog.py --reset

Prérequis
---------
    - DATABASE_URL, SUPABASE_URL, SUPABASE_SERVICE_KEY définis dans backend/.env
    - Dossier backend/scripts/fabric_images/ contenant les photos (voir ci-dessous)
    - pip install psycopg2-binary python-dotenv supabase

Structure des photos attendue
------------------------------
    backend/scripts/fabric_images/
        bazin_riche.jpg
        wax_hollandais.jpg
        kente.jpg
        satin_duchesse.jpg
        dentelle_brodee.jpg
        coton_popeline.jpg
        lin_naturel.jpg
        velours_coton.jpg
        jersey_coton.jpg
        soie_naturelle.jpg
        mousseline_polyester.jpg
        simili_cuir.jpg

Si une image est absente, le tissu est quand même créé (sans photo).
"""

import argparse
import mimetypes
import os
import sys
import uuid
from pathlib import Path

# ---------------------------------------------------------------------------
# Bootstrap : charger .env et ajouter le répertoire backend/ au PYTHONPATH
# ---------------------------------------------------------------------------

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

env_file = BACKEND_DIR / ".env"
if env_file.exists():
    from dotenv import load_dotenv
    load_dotenv(env_file)
    print(f"✓ .env chargé depuis {env_file}")

DATABASE_URL = os.environ.get("DATABASE_URL", "")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = (
    os.environ.get("SUPABASE_SERVICE_KEY")
    or os.environ.get("SUPABASE_KEY")
    or ""
)
IMAGES_DIR = Path(__file__).parent / "fabric_images"
BUCKET_NAME = "fabric_photos"

# ---------------------------------------------------------------------------
# Données réelles des tissus
# ---------------------------------------------------------------------------

# Format des catégories :
#   (nom, description, rigidity_level)  — rigidity_level ∈ {rigid, semi-stretch, stretch}

CATEGORIES = [
    (
        "Tissus Africains Traditionnels",
        "Tissus à motifs caractéristiques de l'artisanat et du commerce africain "
        "(wax, kente, bazin, mudcloth…). Utilisés pour les tenues de cérémonie et "
        "les vêtements du quotidien haut de gamme.",
        "rigid",
    ),
    (
        "Tissus Habillage & Élégance",
        "Tissus à surface lisse ou brillante pour vêtements formels, robes de soirée "
        "et costumes : satin, soie, dentelle, mousseline.",
        "semi-stretch",
    ),
    (
        "Tissus Coton & Lin Courant",
        "Tissus naturels respirants pour confections quotidiennes, chemises, robes "
        "décontractées et tenues de travail.",
        "rigid",
    ),
    (
        "Tissus Stretch & Jersey",
        "Tissus extensibles pour vêtements près du corps, sportswear, bodys "
        "et tops moulants.",
        "stretch",
    ),
    (
        "Tissus Techniques & Synthétiques",
        "Tissus synthétiques ou mixtes aux propriétés spécifiques : imperméabilité, "
        "imitation cuir, polyester haute brillance.",
        "rigid",
    ),
]

# Format des tissus :
#   (nom, elasticite_%, poids_g/m², composition, prix_FCFA/m, fichier_image, catégorie_index)
#   catégorie_index = position dans CATEGORIES (0-based)

FABRICS = [
    # ── Catégorie 0 : Tissus Africains Traditionnels ──────────────────────
    (
        "Bazin Riche",
        4.0,
        280.0,
        "100 % coton mercerisé",
        3500.0,
        "bazin_riche.jpg",
        0,
    ),
    (
        "Wax Hollandais (Vlisco)",
        2.5,
        230.0,
        "100 % coton",
        6000.0,
        "wax_hollandais.jpg",
        0,
    ),
    (
        "Kente Tissé Main",
        1.5,
        320.0,
        "70 % coton, 30 % soie",
        8500.0,
        "kente.jpg",
        0,
    ),
    (
        "Wax Africain Ordinaire",
        3.0,
        210.0,
        "100 % coton",
        2500.0,
        "wax_africain.jpg",
        0,
    ),
    # ── Catégorie 1 : Tissus Habillage & Élégance ─────────────────────────
    (
        "Satin Duchesse",
        8.0,
        160.0,
        "80 % polyester, 20 % nylon",
        2800.0,
        "satin_duchesse.jpg",
        1,
    ),
    (
        "Dentelle Brodée",
        12.0,
        120.0,
        "65 % polyester, 35 % coton",
        4500.0,
        "dentelle_brodee.jpg",
        1,
    ),
    (
        "Soie Naturelle",
        6.0,
        90.0,
        "100 % soie",
        9500.0,
        "soie_naturelle.jpg",
        1,
    ),
    (
        "Mousseline de Polyester",
        5.0,
        75.0,
        "100 % polyester",
        1800.0,
        "mousseline_polyester.jpg",
        1,
    ),
    # ── Catégorie 2 : Tissus Coton & Lin Courant ──────────────────────────
    (
        "Coton Popeline",
        3.0,
        120.0,
        "100 % coton",
        1200.0,
        "coton_popeline.jpg",
        2,
    ),
    (
        "Lin Naturel",
        2.0,
        185.0,
        "100 % lin",
        2200.0,
        "lin_naturel.jpg",
        2,
    ),
    (
        "Velours Coton",
        10.0,
        350.0,
        "85 % coton, 15 % polyester",
        3200.0,
        "velours_coton.jpg",
        2,
    ),
    (
        "Coton Oxford",
        2.5,
        150.0,
        "100 % coton",
        1400.0,
        "coton_oxford.jpg",
        2,
    ),
    # ── Catégorie 3 : Tissus Stretch & Jersey ─────────────────────────────
    (
        "Jersey Coton",
        45.0,
        180.0,
        "95 % coton, 5 % élasthanne",
        1600.0,
        "jersey_coton.jpg",
        3,
    ),
    (
        "Jersey Milano",
        35.0,
        200.0,
        "70 % viscose, 25 % polyamide, 5 % élasthanne",
        2400.0,
        "jersey_milano.jpg",
        3,
    ),
    (
        "Lycra / Spandex",
        80.0,
        220.0,
        "80 % polyester, 20 % élasthanne",
        2600.0,
        "lycra_spandex.jpg",
        3,
    ),
    # ── Catégorie 4 : Tissus Techniques & Synthétiques ────────────────────
    (
        "Simili Cuir (Faux Cuir)",
        5.0,
        450.0,
        "PU (polyuréthane) sur base tissée polyester",
        4200.0,
        "simili_cuir.jpg",
        4,
    ),
    (
        "Polyester Mikado",
        4.0,
        190.0,
        "100 % polyester",
        2000.0,
        "polyester_mikado.jpg",
        4,
    ),
]


# ---------------------------------------------------------------------------
# Helpers DB (psycopg2 synchrone)
# ---------------------------------------------------------------------------

def get_db_conn(url: str):
    import psycopg2
    sync_url = url.replace("postgresql+asyncpg://", "postgresql://", 1)
    return psycopg2.connect(sync_url)


def reset_fabric_data(conn) -> None:
    """Supprime tous les tissus et catégories existants (CASCADE)."""
    with conn.cursor() as cur:
        cur.execute("DELETE FROM fabrics;")
        cur.execute("DELETE FROM fabric_categories;")
    conn.commit()
    print("✓ Données existantes supprimées (reset).")


def insert_category(conn, name: str, description: str, rigidity: str) -> str:
    """Insère une catégorie et retourne son UUID."""
    cat_id = str(uuid.uuid4())
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO fabric_categories
                (category_id, category_name, category_description, reference_rigidity_level)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (category_id) DO NOTHING;
            """,
            (cat_id, name, description, rigidity),
        )
    conn.commit()
    return cat_id


def insert_fabric(
    conn,
    fabric_id: str,
    name: str,
    elasticity: float,
    weight: float,
    composition: str,
    price: float,
    category_id: str,
    photo_url: str | None,
) -> None:
    """Insère un tissu avec toutes ses propriétés."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO fabrics
                (fabric_id, fabric_name, fabric_elasticity_rate, fabric_weight,
                 fabric_composition, fabric_unit_price, fabric_photo,
                 fabric_status, category_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'available', %s)
            ON CONFLICT (fabric_id) DO NOTHING;
            """,
            (
                fabric_id, name, elasticity, weight,
                composition, price, photo_url, category_id,
            ),
        )
    conn.commit()


# ---------------------------------------------------------------------------
# Helpers Supabase Storage
# ---------------------------------------------------------------------------

def upload_image(fabric_id: str, image_path: Path) -> str | None:
    """Upload une image vers Supabase Storage et retourne l'URL publique."""
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        print("    ⚠  SUPABASE_URL / SUPABASE_SERVICE_KEY manquants — photo ignorée.")
        return None

    try:
        from supabase import create_client
    except ImportError:
        print("    ⚠  Package 'supabase' non installé (pip install supabase) — photo ignorée.")
        return None

    if not image_path.exists():
        print(f"    ⚠  Image introuvable : {image_path.name} — tissu créé sans photo.")
        return None

    content_type, _ = mimetypes.guess_type(str(image_path))
    content_type = content_type or "image/jpeg"
    ext = image_path.suffix.lstrip(".")
    storage_path = f"{fabric_id}/{uuid.uuid4()}.{ext}"

    try:
        client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
        with open(image_path, "rb") as f:
            file_bytes = f.read()

        client.storage.from_(BUCKET_NAME).upload(
            storage_path,
            file_bytes,
            {"content-type": content_type, "upsert": "true"},
        )

        # URL publique
        public_url = (
            f"{SUPABASE_URL.rstrip('/')}/storage/v1/object/public/"
            f"{BUCKET_NAME}/{storage_path}"
        )
        return public_url

    except Exception as exc:
        print(f"    ⚠  Échec upload ({image_path.name}) : {exc} — tissu créé sans photo.")
        return None


def ensure_bucket_exists() -> None:
    """Crée le bucket fabric_photos s'il n'existe pas (public)."""
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        return
    try:
        from supabase import create_client
        client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
        buckets = [b.name for b in client.storage.list_buckets()]
        if BUCKET_NAME not in buckets:
            client.storage.create_bucket(BUCKET_NAME, options={"public": True})
            print(f"✓ Bucket '{BUCKET_NAME}' créé.")
        else:
            print(f"✓ Bucket '{BUCKET_NAME}' déjà existant.")
    except Exception as exc:
        print(f"⚠  Impossible de vérifier/créer le bucket : {exc}")


# ---------------------------------------------------------------------------
# Point d'entrée principal
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Seed du catalogue de tissus Lova Fashion")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Supprime les données existantes avant d'insérer (ATTENTION : irréversible).",
    )
    args = parser.parse_args()

    # Vérifications
    if not DATABASE_URL:
        print("ERREUR : DATABASE_URL n'est pas défini dans .env", file=sys.stderr)
        sys.exit(1)

    try:
        import psycopg2  # noqa: F401
    except ImportError:
        print("ERREUR : psycopg2-binary n'est pas installé.\n  pip install psycopg2-binary", file=sys.stderr)
        sys.exit(1)

    print("\n=== Seed Catalogue de Tissus — Lova Fashion ===\n")

    # Connexion DB
    print("Connexion à la base de données…")
    try:
        conn = get_db_conn(DATABASE_URL)
    except Exception as exc:
        print(f"ERREUR de connexion : {exc}", file=sys.stderr)
        sys.exit(1)
    print("✓ Connecté.\n")

    # Reset optionnel
    if args.reset:
        print("⚠  Mode RESET activé.")
        reset_fabric_data(conn)

    # Bucket Supabase Storage
    print("Vérification du bucket Supabase Storage…")
    ensure_bucket_exists()
    print()

    # ── Insérer les catégories ────────────────────────────────────────────
    print(f"Insertion de {len(CATEGORIES)} catégories…")
    category_ids: list[str] = []
    for i, (name, desc, rigidity) in enumerate(CATEGORIES):
        cat_id = insert_category(conn, name, desc, rigidity)
        category_ids.append(cat_id)
        print(f"  [{i+1}/{len(CATEGORIES)}] ✓ {name}  (id: {cat_id})")
    print()

    # ── Insérer les tissus ────────────────────────────────────────────────
    print(f"Insertion de {len(FABRICS)} tissus…")
    for i, (name, elasticity, weight, composition, price, img_file, cat_idx) in enumerate(FABRICS):
        fabric_id = str(uuid.uuid4())
        category_id = category_ids[cat_idx]

        print(f"  [{i+1}/{len(FABRICS)}] {name}")
        print(f"    Composition : {composition}")
        print(f"    Élasticité  : {elasticity} %  |  Poids : {weight} g/m²  |  Prix : {price:,.0f} FCFA/m")

        # Upload de la photo
        image_path = IMAGES_DIR / img_file
        photo_url = upload_image(fabric_id, image_path)
        if photo_url:
            print(f"    Photo       : {photo_url[:80]}…")

        # Insertion DB
        insert_fabric(
            conn, fabric_id, name, elasticity, weight,
            composition, price, category_id, photo_url,
        )
        print(f"    ✓ Inséré  (id: {fabric_id})")

    conn.close()

    print(f"\n✓ Seed terminé — {len(CATEGORIES)} catégories, {len(FABRICS)} tissus insérés.")
    print("\nPour ajouter/remplacer les photos :")
    print(f"  Placez les images JPEG/PNG dans : {IMAGES_DIR}")
    print("  Puis relancez : python scripts/seed_fabric_catalog.py --reset")


if __name__ == "__main__":
    main()
