# Entity-Relationship Diagram (ER)

## Relationships

| Entity A | Cardinality | Entity B | Description |
|----------|-------------|----------|-------------|
| ADMINISTRATOR | \|\|--o{ | COMPATIBILITY_RULE | creates/updates |
| COMPATIBILITY_RULE | \|\|--o{ | VERDICT_EVALUATION | applied in |
| VERDICT_EVALUATION | \|\|--\|{ | RISK_ZONE | generates |
| VERDICT_EVALUATION | }o--\|\| | MODEL | evaluates (Module 4) |
| COMPATIBILITY_RULE | }o--\|\| | CRITICAL_ZONE | targets (Module 4) |
| RISK_ZONE | }o--\|\| | CRITICAL_ZONE | affects (Module 4) |
| VERDICT_EVALUATION | }o--\|\| | MEASUREMENTS | uses (Module 5) |
| VERDICT_EVALUATION | }o--\|\| | FABRIC | considers (Module 3) |
| VERDICT_EVALUATION | }o--\|\| | MORPHOLOGY | evaluates user morphology |
| MODEL | \|\|--o{ | MODEL_FABRIC_LINK | has recommended fabrics |
| FABRIC | \|\|--o{ | MODEL_FABRIC_LINK | looks fine on |
| MODEL | \|\|--o{ | MODEL_MORPHOLOGY_LINK | suits well to |
| MORPHOLOGY | \|\|--o{ | MODEL_MORPHOLOGY_LINK | is suited for |

---

# Entities

## COMPATIBILITY_RULE

| Attribute | Type | Description |
|----------|------|-------------|
| rule_id | string (PK) | Unique rule identifier |
| cut_type | string | e.g., Fitted, Loose |
| fabric_property | string | e.g., Rigid, Stretch > 2% |
| zone_id | string (FK) | References **CRITICAL_ZONE** (Module 4) |
| mathematical_condition | string | e.g., ratio > 1.4 |
| severity_level | string | Incompatible, Reserve |
| explanation_message | string | Message displayed to the client |
| is_active | boolean | Indicates whether the rule is active |
| version | int | Rule version |
| admin_id | string (FK) | References the administrator |

---

## VERDICT_EVALUATION

| Attribute | Type | Description |
|----------|------|-------------|
| evaluation_id | string (PK) | Unique evaluation identifier |
| created_at | datetime | Evaluation creation date and time |
| global_status | string | Compatible, Incompatible, Reserve, Failed |
| missing_data_log | string | Missing data information if the evaluation failed |
| client_id | string | Reference to the end user |
| model_id | string (FK) | References **MODEL** (Module 4) |
| fabric_id | string (FK) | References **FABRIC** (Module 3) |
| measurements_id | string (FK) | References **MEASUREMENTS** (Module 5) |
| morphology_id | string (FK) | References **MORPHOLOGY** |

---

## RISK_ZONE

| Attribute | Type | Description |
|----------|------|-------------|
| risk_id | string (PK) | Unique risk identifier |
| evaluation_id | string (FK) | References the evaluation |
| rule_id | string (FK) | References the applied compatibility rule |
| zone_id | string (FK) | References **CRITICAL_ZONE** (Module 4) |
| calculated_variance | float | Computed mathematical variance |
| localized_verdict | string | Incompatible, Reserve |
| explanation | string | Explanation inherited from the compatibility rule |

---

# Association Tables

## MODEL_FABRIC_LINK

| Attribute | Type | Description |
|----------|------|-------------|
| model_id | string (FK) | References **MODEL** |
| fabric_id | string (FK) | References **FABRIC** |
| recommendation_level | string | e.g., Highly Recommended, Accepted |

---

## MODEL_MORPHOLOGY_LINK

| Attribute | Type | Description |
|----------|------|-------------|
| model_id | string (FK) | References **MODEL** |
| morphology_id | string (FK) | References **MORPHOLOGY** |
| suitability_score | string | e.g., Ideal, Flattering, Avoid |

