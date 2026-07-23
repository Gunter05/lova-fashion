# Conceptual Data Model (CDM) — Fabric & Measurement Adjustment

## Entities

### TISSU_REFERENCE (FABRIC_REFERENCE)

| Attribute | Type | Key |
|---|---|---|
| id_tissu (fabric_id) | INTEGER | Primary Key |
| nom_tissu (fabric_name) | VARCHAR(100) | |
| categorie_elasticite (elasticity_category) | VARCHAR(100) | |
| valeur_aisance_defaut (default_ease_value) | DECIMAL | |

### AJUSTEMENT_MENSURATION (MEASUREMENT_ADJUSTMENT)

| Attribute | Type | Key |
|---|---|---|
| id_ajustement (adjustment_id) | INTEGER | Primary Key |
| tour_poitrine_ajuste (adjusted_chest_circumference) | DECIMAL | |
| tour_taille_ajuste (adjusted_waist_circumference) | DECIMAL | |
| tour_hanches_ajuste (adjusted_hip_circumference) | DECIMAL | |
| marge_appliquee_cm (applied_margin_cm) | DECIMAL | |
| date_calcul (calculation_date) | DATETIME | |
| id_mesure_brute (raw_measurement_id) | INTEGER | Foreign Key |

## Relationship

### appliquer (apply)

Connects **TISSU_REFERENCE** to **AJUSTEMENT_MENSURATION**.

- **TISSU_REFERENCE → appliquer**: cardinality **1,n** (one fabric reference can be applied to many measurement adjustments; each adjustment is linked to at least one fabric).
- **appliquer → AJUSTEMENT_MENSURATION**: cardinality **1,1** (each measurement adjustment results from applying exactly one fabric reference).

## Textual Representation

```
TISSU_REFERENCE (1,n) ────── appliquer ────── (1,1) AJUSTEMENT_MENSURATION
```

A single fabric reference can be used to compute ease-allowance adjustments for many different measurement records, but each individual measurement adjustment is always based on exactly one fabric reference.
