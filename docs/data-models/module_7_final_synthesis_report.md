# Conceptual Data Model (MCD) — Module 7: Measurement Reports & Recommendations

## Entities & Attributes

### 1. Measurement Report (`Rapport_mesure`)
* **`id_report`**: VARCHAR(50) — *Primary Key*
* **`generated_at`**: DATE
* **`adjusted_measurements`**: TEXT
* **`verdict`**: TEXT
* **`advice`**: TEXT

### 2. Body Measurement (`Mensuration`)
* **`id_measurement`**: VARCHAR(50) — *Primary Key*
* **`taken_at`**: DATE
* **`waist_circumference`**: DECIMAL
* **`bust_circumference`**: DECIMAL
* **`arm_length`**: DECIMAL
* **`waist_length`**: DECIMAL
* **`bust_height`**: DECIMAL
* **`hip_circumference`**: DECIMAL
* **`thigh_circumference`**: DECIMAL

### 3. Fabric (`Tissu`)
* **`id_fabric`**: VARCHAR(50) — *Primary Key*
* **`name`**: VARCHAR(50)
* **`colors`**: VARCHAR(50)

### 4. Garment Model (`Modèle`)
* **`id_model`**: VARCHAR(50) — *Primary Key*
* **`name`**: VARCHAR(50)
* **`description`**: VARCHAR(50)
* **`photo_link`**: VARCHAR(50)

---

## Relationships & Cardinalities

1. **Mensuration — Rapport_mesure** (`generate` / *générer*)
   * `Mensuration` (0,N) <---> (1,1) `Rapport_mesure`
   * *A body measurement set can generate multiple reports over time; a report is generated from 1 measurement set.*

2. **Rapport_mesure — Tissu** (`take_into_account` / *tenir compte*)
   * `Rapport_mesure` (1,1) <---> (0,N) `Tissu`
   * *A measurement report takes into account 1 fabric; a fabric can be referenced in multiple reports.*

3. **Rapport_mesure — Modèle** (`apply_to` / *s'appliquer*)
   * `Rapport_mesure` (1,1) <---> (0,N) `Modèle`
   * *A measurement report applies to 1 garment model; a garment model can have multiple reports applied to it.*