# Requirements — Module 5: Ease Allowance Calculation Engine
# (Moteur de calcul d'aisance)

## Overview

This module takes an authenticated user's active raw measurement profile (bust, waist,
hips in cm — produced by Module 2) and a chosen fabric (from Module 3) and computes the
final garment-cutting dimensions by applying a fabric-specific ease allowance. The result
is persisted as a `measurement_adjustment` record and returned immediately to the caller
for frontend rendering and downstream consumption by Module 7 (Final Result / Report).

---

## Actors

| Actor | Description |
|---|---|
| **Authenticated User** | End client who has completed a capture session and selects a fabric |
| **System (Ease Engine)** | Applies the mathematical adjustment rule based on fabric elasticity |
| **Module 2 — Measurements** | Upstream source of `raw_measurements` (read-only by this module) |
| **Module 3 — Fabric Catalog** | Upstream source of fabric elasticity data (read-only by this module) |
| **Module 7 — Final Report** | Downstream consumer of the `measurement_adjustments` records |

---

## User Stories & Acceptance Criteria (EARS Format)

---

### US-01 — Request an Ease Adjustment

**As an** authenticated user,  
**I want to** submit a `(session_id, fabric_id)` pair to the ease engine,  
**so that** I receive the final garment measurements for that specific fabric immediately.

#### AC-01.1 — Requires authentication
> **When** a request to compute an adjustment is received without a valid JWT,  
> **the system shall** return HTTP 401 Unauthorized.

#### AC-01.2 — Session must exist and belong to the caller
> **When** the supplied `session_id` does not exist or belongs to a different user,  
> **the system shall** return HTTP 404 Not Found or HTTP 403 Forbidden respectively.

#### AC-01.3 — Session must have a completed measurement
> **When** the supplied `session_id` refers to a capture session whose status is not
> `success` (i.e., no `raw_measurements` row exists yet),  
> **the system shall** return HTTP 424 Failed Dependency with the message  
> `"Aucune mensuration validée pour cette session. Complétez d'abord la prise de mesure."`.

#### AC-01.4 — Fabric must exist in the catalog
> **When** the supplied `fabric_id` does not match any record in the fabric catalog,  
> **the system shall** return HTTP 404 with the message  
> `"Tissu introuvable dans le catalogue."`.

#### AC-01.5 — Adjustment is computed and returned synchronously
> **When** all inputs are valid,  
> **the system shall** compute the adjustment, persist it, and return HTTP 201 with the
> full `AdjustmentResponse` payload within a single synchronous request.

#### AC-01.6 — Idempotent re-computation for same (session, fabric) pair
> **When** an adjustment for the same `(session_id, fabric_id)` pair already exists,  
> **the system shall** recalculate and **overwrite** the existing record (upsert),
> returning HTTP 200 with the updated payload.  
> This allows the user to recompute after a fabric record is corrected.

---

### US-02 — Ease Rules by Elasticity Category

**As the** ease calculation engine,  
**I want to** apply the correct ease delta based on the fabric's elasticity category,  
**so that** the adjusted measurements accurately reflect the physical behaviour of
the chosen textile.

#### AC-02.1 — Rigid fabric applies +4 cm ease
> **When** the fabric's elasticity category is `rigid`,  
> **the system shall** add **+4.0 cm** to each measurement zone (bust, waist, hips).

#### AC-02.2 — Semi-stretch fabric applies +2 cm ease
> **When** the fabric's elasticity category is `semi-stretch`,  
> **the system shall** add **+2.0 cm** to each measurement zone.

#### AC-02.3 — Stretch fabric applies −2 cm ease
> **When** the fabric's elasticity category is `stretch`,  
> **the system shall** subtract **2.0 cm** from each measurement zone.

#### AC-02.4 — Unknown or missing elasticity applies default +3 cm with system warning
> **When** the fabric's elasticity category is absent or holds a value other than
> `rigid`, `semi-stretch`, or `stretch`,  
> **the system shall** apply a default ease of **+3.0 cm** to all zones,
> persist the adjustment with `ease_source = "default_fallback"`,
> and emit a structured system warning log entry (level `WARNING`) for administrator review.  
> The user-facing response is not blocked; the adjustment is returned normally.

---

### US-03 — Per-Zone Ease Storage

**As the** ease calculation engine,  
**I want to** store the applied ease margin per individual measurement zone,  
**so that** future per-zone override rules can be introduced without a schema migration.

#### AC-03.1 — Each zone's applied margin is persisted independently
> **When** an adjustment is computed,  
> **the system shall** store the applied ease value separately for each zone
> (`bust_ease_cm`, `waist_ease_cm`, `hips_ease_cm`) on the adjustment record,
> even when all three are identical (default uniform rule).

#### AC-03.2 — Adjusted values and raw values are both stored
> **When** an adjustment is persisted,  
> **the system shall** store both the raw input values (`raw_bust_cm`, `raw_waist_cm`,
> `raw_hips_cm`) and the adjusted output values (`adjusted_bust_cm`,
> `adjusted_waist_cm`, `adjusted_hips_cm`) on the same record for full auditability.

---

### US-04 — Floor Constraint

**As the** ease calculation engine,  
**I want to** enforce a minimum adjusted measurement value,  
**so that** arithmetically invalid results (e.g., negative measurements from bad CV data)
never reach Module 7 or the tailor.

#### AC-04.1 — Adjusted measurement is never below 0 cm
> **When** applying the ease delta would produce a value less than 0 cm,  
> **the system shall** clamp the adjusted value to **0.0 cm**.

#### AC-04.2 — Warning logged when adjusted value falls below 30 cm
> **When** an adjusted measurement, after clamping, is greater than 0 cm but less
> than 30 cm,  
> **the system shall** emit a structured system warning log entry (level `WARNING`)
> identifying the zone and the computed value, indicating potentially unreliable
> input data from the CV pipeline.

---

### US-05 — View a Specific Adjustment

**As an** authenticated user,  
**I want to** retrieve an existing adjustment record by its ID,  
**so that** I can review the calculation details or share them with a tailor.

#### AC-05.1 — Returns full adjustment detail
> **When** an authenticated user calls `GET /adjustments/{adjustment_id}`,  
> **the system shall** return HTTP 200 with the full `AdjustmentResponse` including
> raw inputs, applied ease per zone, adjusted outputs, fabric name, and `ease_source`.

#### AC-05.2 — Ownership enforced on retrieval
> **When** the adjustment belongs to a session owned by a different user,  
> **the system shall** return HTTP 403 Forbidden.

---

### US-06 — List Adjustments for a Session

**As an** authenticated user,  
**I want to** list all adjustments computed for a given session,  
**so that** I can compare how different fabrics affect my final cutting measurements.

#### AC-06.1 — Returns all adjustments for the session, newest first
> **When** an authenticated user calls `GET /sessions/{session_id}/adjustments`,  
> **the system shall** return HTTP 200 with a list of `AdjustmentSummary` objects
> ordered by `calculated_at` descending.

#### AC-06.2 — Empty list when no adjustments exist
> **When** no adjustments have been computed for the session yet,  
> **the system shall** return HTTP 200 with an empty `adjustments` array and `total: 0`.

---

### US-07 — No Active Measurement Guard

**As the** ease calculation engine,  
**I want to** explicitly reject requests made before a user has a valid measurement,  
**so that** Module 7 never receives an adjustment built on missing or stale data.

#### AC-07.1 — Rejects computation when session has no raw measurement
> Covered by AC-01.3. Restated here for Module 7 integration clarity:  
> **When** downstream calls to Module 7 reference an adjustment whose source session
> is no longer in `success` status,  
> **the system shall** include a `data_integrity_warning` flag in the adjustment
> response payload.

---

## Non-Functional Requirements

| ID | Requirement |
|---|---|
| NFR-01 | The adjustment computation must complete within **500 ms** (pure arithmetic — no external I/O beyond the two DB reads). |
| NFR-02 | All endpoints require `Authorization: Bearer <JWT>` (NFR-03 parity with Module 2). |
| NFR-03 | `measurement_adjustments` RLS policy: users may only read/write rows whose `session_id` maps to a session they own. |
| NFR-04 | Adjusted measurements use `DECIMAL(5,1)` precision (one decimal place), consistent with Module 2 raw values. |
| NFR-05 | All error responses follow the `{"detail": "<message>"}` envelope (French). |
| NFR-06 | The `ease_rules` reference table is seeded at migration time and never modified at runtime by the application. |
