#!/usr/bin/env python3
"""
compress_fabric_images.py — Compresse les images du catalogue de tissus
                             avec une cible de taille en Ko (défaut : 150 Ko).

Usage
-----
    cd backend
    pip install Pillow
    python scripts/compress_fabric_images.py

    # Aperçu sans écriture
    python scripts/compress_fabric_images.py --dry-run

    # Cible différente (ex : 100 Ko)
    python scripts/compress_fabric_images.py --max-kb 100

    # Remplace les originaux directement (sans suffixe _opt)
    python scripts/compress_fabric_images.py --replace

Stratégie
---------
    1. Redimensionne à 800×800 px max (ratio conservé, LANCZOS)
    2. Essaie qualité 85 → descend par pas de 5 jusqu'à atteindre la cible
    3. Si la cible n'est pas atteinte à qualité 40, réduit la résolution
       (700px, 600px, 500px) et recommence la boucle qualité
    4. Sauvegarde en JPEG progressif optimisé
"""

import argparse
import io
import sys
from pathlib import Path

IMAGES_DIR   = Path(__file__).parent / "fabric_images"
MAX_PX       = 800          # résolution max initiale (px)
MIN_PX       = 400          # résolution plancher (en dessous on ne réduit plus)
PX_STEP      = 100          # réduction de résolution si qualité insuffisante
QUALITY_START = 85          # qualité de départ
QUALITY_MIN   = 40          # qualité plancher avant de réduire la résolution
QUALITY_STEP  = 5           # pas de descente de qualité
DEFAULT_MAX_KB = 150        # cible en Ko
SUFFIX        = "_opt"
EXTENSIONS    = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff"}


def _encode(img, quality: int) -> bytes:
    """Encode l'image PIL en JPEG en mémoire et retourne les bytes."""
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality, optimize=True, progressive=True)
    return buf.getvalue()


def compress_to_target(src: Path, max_kb: int, dry_run: bool, replace: bool) -> None:
    """Compresse src jusqu'à atteindre max_kb Ko, ou s'en approche au mieux."""
    try:
        from PIL import Image
    except ImportError:
        print("ERREUR : Pillow n'est pas installé.\n  pip install Pillow", file=sys.stderr)
        sys.exit(1)

    target_bytes = max_kb * 1024
    src_bytes    = src.stat().st_size

    with Image.open(src) as img_orig:
        if img_orig.mode not in ("RGB", "L"):
            img_orig = img_orig.convert("RGB")
        original_size = img_orig.size

        best_data    = None
        best_quality = QUALITY_START
        best_px      = MAX_PX
        reached      = False

        # Boucle sur les résolutions décroissantes
        for max_px in range(MAX_PX, MIN_PX - 1, -PX_STEP):
            img = img_orig.copy()
            img.thumbnail((max_px, max_px), Image.LANCZOS)

            # Boucle sur les qualités décroissantes
            for quality in range(QUALITY_START, QUALITY_MIN - 1, -QUALITY_STEP):
                data = _encode(img, quality)
                if best_data is None or len(data) < len(best_data):
                    best_data    = data
                    best_quality = quality
                    best_px      = max_px
                if len(data) <= target_bytes:
                    reached = True
                    break

            if reached:
                break

        final_kb  = len(best_data) / 1024
        saving    = (1 - len(best_data) / src_bytes) * 100
        new_size  = Image.open(io.BytesIO(best_data)).size

        status = "✓" if reached else "⚠ "
        note   = "" if reached else f"  (cible {max_kb} Ko non atteinte — meilleur résultat)"

        if dry_run:
            print(f"  [dry-run] {src.name}")
            print(f"    {original_size[0]}×{original_size[1]} → {new_size[0]}×{new_size[1]} px")
            print(f"    {src_bytes / 1024:.0f} Ko  →  {final_kb:.0f} Ko  "
                  f"({saving:+.0f} %)  qualité {best_quality}{note}")
            return

        if replace:
            dest = src.with_suffix(".jpg")
        else:
            dest = src.with_stem(src.stem + SUFFIX).with_suffix(".jpg")

        dest.write_bytes(best_data)

        print(f"  {status} {src.name}")
        print(f"    {original_size[0]}×{original_size[1]} → {new_size[0]}×{new_size[1]} px  "
              f"| qualité {best_quality}")
        print(f"    {src_bytes / 1024:.0f} Ko  →  {final_kb:.0f} Ko  ({saving:+.0f} %){note}")
        print(f"    → {dest.name}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compresse les images tissu avec cible de taille"
    )
    parser.add_argument("--max-kb",  type=int,  default=DEFAULT_MAX_KB,
                        help=f"Taille cible en Ko (défaut : {DEFAULT_MAX_KB})")
    parser.add_argument("--dry-run", action="store_true",
                        help="Affiche les infos sans écrire de fichier")
    parser.add_argument("--replace", action="store_true",
                        help="Remplace les originaux (sans suffixe _opt)")
    parser.add_argument("--dir",     type=Path, default=IMAGES_DIR,
                        help="Dossier source (défaut : scripts/fabric_images/)")
    args = parser.parse_args()

    images_dir: Path = args.dir
    if not images_dir.exists():
        print(f"ERREUR : Dossier introuvable : {images_dir}", file=sys.stderr)
        sys.exit(1)

    images = [p for p in sorted(images_dir.iterdir())
              if p.suffix.lower() in EXTENSIONS and not p.stem.endswith(SUFFIX)]

    if not images:
        print(f"Aucune image trouvée dans {images_dir}")
        return

    mode = "DRY-RUN" if args.dry_run else ("remplacement" if args.replace else "copies _opt")
    print(f"\n=== Compression images tissus — cible {args.max_kb} Ko ({mode}) ===\n")
    print(f"Dossier : {images_dir}")
    print(f"Images  : {len(images)} fichier(s)\n")

    total_before = total_after = 0

    for img_path in images:
        compress_to_target(img_path, args.max_kb, args.dry_run, args.replace)
        if not args.dry_run:
            total_before += img_path.stat().st_size
            suffix = "" if args.replace else SUFFIX
            opt = img_path.with_stem(img_path.stem + suffix).with_suffix(".jpg")
            if opt.exists():
                total_after += opt.stat().st_size
        print()

    if not args.dry_run and total_before:
        saving = (1 - total_after / total_before) * 100
        print("─────────────────────────────────────────")
        print(f"Total avant : {total_before / 1024:.0f} Ko")
        print(f"Total après : {total_after  / 1024:.0f} Ko")
        print(f"Gain global : {saving:.0f} %\n")
        if not args.replace:
            print("Les fichiers *_opt.jpg sont prêts. Une fois vérifiés :")
            print("  python scripts/compress_fabric_images.py --replace")
            print("  python scripts/seed_fabric_catalog.py --reset")


if __name__ == "__main__":
    main()
