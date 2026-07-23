# Conceptual Data Model (CDM) — Capture Session & Raw Measurement

## Entities

### SESSION_CAPTURE (CAPTURE_SESSION)

| Attribute | Type | Key |
|---|---|---|
| id_capture (capture_id) | INTEGER | Primary Key |
| photo_face_url (front_photo_url) | VARCHAR(100) | |
| photo_profil_url (profile_photo_url) | VARCHAR(100) | |
| stature_saisie (entered_stature) | DECIMAL | |
| date_session (session_date) | DATETIME | |

### MESURATION_BRUTE (RAW_MEASUREMENT)

| Attribute | Type | Key |
|---|---|---|
| id_mesure_brute (raw_measurement_id) | INTEGER | Primary Key |
| tour_poitrine_brut (raw_chest_circumference) | DECIMAL | |
| tour_taille_brut (raw_waist_circumference) | DECIMAL | |
| tour_hanches_brut (raw_hip_circumference) | DECIMAL | |

### MORPHOLOGIE (BODY_SHAPE)

| Attribute | Type | Key |
|---|---|---|
| code_silhouette (silhouette_code) | VARCHAR(100) | Primary Key |
| nom_silhouette (silhouette_name) | VARCHAR(100) | |
| description_ratios (ratio_description) | TEXT | |

## Relationships

### PRODUIRE (PRODUCE)

Connects **SESSION_CAPTURE** to **MESURATION_BRUTE**.

- **SESSION_CAPTURE → PRODUIRE**: cardinality **1,1** (each capture session produces exactly one raw measurement).
- **PRODUIRE → MESURATION_BRUTE**: cardinality **1,1** (each raw measurement originates from exactly one capture session).

### CARACTERISER (CHARACTERIZE)

Connects **MESURATION_BRUTE** to **MORPHOLOGIE**.

- **MESURATION_BRUTE → CARACTERISER**: cardinality **1,1** (each raw measurement is characterized by exactly one body shape).
- **CARACTERISER → MORPHOLOGIE**: cardinality **0,n** (a body shape may characterize zero to many raw measurements).

## Textual Representation

```
SESSION_CAPTURE (1,1) ── PRODUIRE ── (1,1) MESURATION_BRUTE (1,1) ── CARACTERISER ── (0,n) MORPHOLOGIE
```

Each capture session generates exactly one raw measurement record. That raw measurement is in turn associated with exactly one body-shape classification, while a given body shape can characterize many different raw measurements (or none yet).
