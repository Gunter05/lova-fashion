# Photos des tissus — Lova Fashion

Placer ici les photos des tissus **avant** de lancer le script de seed.

## Noms de fichiers attendus

| Fichier                  | Tissu                         | Catégorie                         |
|--------------------------|-------------------------------|-----------------------------------|
| `bazin_riche.jpg`        | Bazin Riche                   | Tissus Africains Traditionnels    |
| `wax_hollandais.jpg`     | Wax Hollandais (Vlisco)       | Tissus Africains Traditionnels    |
| `kente.jpg`              | Kente Tissé Main              | Tissus Africains Traditionnels    |
| `wax_africain.jpg`       | Wax Africain Ordinaire        | Tissus Africains Traditionnels    |
| `satin_duchesse.jpg`     | Satin Duchesse                | Tissus Habillage & Élégance       |
| `dentelle_brodee.jpg`    | Dentelle Brodée               | Tissus Habillage & Élégance       |
| `soie_naturelle.jpg`     | Soie Naturelle                | Tissus Habillage & Élégance       |
| `mousseline_polyester.jpg` | Mousseline de Polyester     | Tissus Habillage & Élégance       |
| `coton_popeline.jpg`     | Coton Popeline                | Tissus Coton & Lin Courant        |
| `lin_naturel.jpg`        | Lin Naturel                   | Tissus Coton & Lin Courant        |
| `velours_coton.jpg`      | Velours Coton                 | Tissus Coton & Lin Courant        |
| `coton_oxford.jpg`       | Coton Oxford                  | Tissus Coton & Lin Courant        |
| `jersey_coton.jpg`       | Jersey Coton                  | Tissus Stretch & Jersey           |
| `jersey_milano.jpg`      | Jersey Milano                 | Tissus Stretch & Jersey           |
| `lycra_spandex.jpg`      | Lycra / Spandex               | Tissus Stretch & Jersey           |
| `simili_cuir.jpg`        | Simili Cuir (Faux Cuir)       | Tissus Techniques & Synthétiques  |
| `polyester_mikado.jpg`   | Polyester Mikado              | Tissus Techniques & Synthétiques  |

## Format recommandé
- **Format** : JPEG ou PNG
- **Résolution** : 800×800 px minimum (carré de préférence)
- **Taille** : < 2 Mo par image
- **Vue** : photo du tissu drapé ou en aplat, lumière neutre

## Sources de photos libres de droits
- [Unsplash](https://unsplash.com) — rechercher "wax fabric", "kente", "bazin", "cotton fabric"
- [Pexels](https://pexels.com) — même termes de recherche
- Photos réelles prises par l'équipe (recommandé pour l'authenticité)

## Lancer le seed

```bash
cd backend
# Premier lancement
python scripts/seed_fabric_catalog.py

# Réinitialiser et re-seeder (efface les données existantes)
python scripts/seed_fabric_catalog.py --reset
```

## Notes
- Si une image est absente, le tissu est quand même créé en base **sans photo**.
- Tu pourras uploader la photo plus tard via l'API :
  `POST /api/v1/fabrics/{fabric_id}/photo` avec le fichier en `multipart/form-data`.
