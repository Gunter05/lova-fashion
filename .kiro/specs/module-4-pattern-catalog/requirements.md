# Requirements Document

## Introduction

The Pattern Catalog module (Module 4) manages the reference catalog of garment model profiles
for the Lova Fashion custom-fit application. Each profile captures the garment type, cut type
(fitted / semi-fitted / loose), constrained body zones, and compatible fabrics, forming the
technical baseline that the Compatibility Engine (Module 6) and the Final Report (Module 7)
rely on.

Profile creation follows a semi-automated, human-in-the-loop workflow: a client uploads an
inspiration image, a synchronous Computer Vision service generates a Draft profile, and an
administrator reviews, completes, and publishes it. Immutability is enforced through full-row
snapshots: every time a Published model is edited and republished, the system atomically
copies the old state into a `MODEL_SNAPSHOT` table before updating the live row, so historical
reports can always reconstruct the exact profile they used.

This module lives in the `auth_catalogues` module group alongside Modules 1 and 3. It assumes
that an already-validated JWT with a `role` claim is present on every request; authentication
is handled by Module 1. Fabrics referenced in this module must exist in and be `available`
within Module 3.

---

## Glossary

| Term | Definition |
|---|---|
| **Model** | A garment profile in the catalog, capturing garment type, cut type, critical zones, and compatible fabrics (e.g., "Sheath Dress — Fitted"). |
| **Draft** | Initial status of a model profile after AI analysis. Not visible to clients or downstream modules. |
| **Published** | A model profile that has been reviewed and explicitly published by an administrator. Visible to clients and consulted by downstream modules. |
| **Archived** | A model profile removed from the active catalog. Returns HTTP 404 to client-facing endpoints; full data is served to internal/downstream endpoints. |
| **Garment type** | The category of the garment, drawn from the enum: `Dress`, `Shirt`, `Blouse`, `Trousers`, `Skirt`, `Jacket`, `Coat`, `Shorts`, `Suit`, `Traditional`. |
| **Cut type** | The degree of closeness of the garment to the body: `Fitted`, `Semi-fitted`, or `Loose`. |
| **Critical zone** | A body part on which the model imposes a measurement constraint (e.g., Chest, Waist, Hips). |
| **Compatible fabric** | A fabric from the Module 3 catalog, with `fabric_status = available`, deemed suitable for the model by an administrator. |
| **Version** | An integer counter on the MODEL row, incremented each time a Published model is edited and republished. Starts at 1. |
| **Snapshot** | An immutable full copy of a MODEL row together with its zone and fabric relations, written to `MODEL_SNAPSHOT` at the moment a Published model is edited. Preserves the exact state used by historical reports. |
| **AI Analyzer** | The synchronous Computer Vision service that analyzes an inspiration image and returns predicted garment type, cut type, and critical zones. |
| **Administrator** | A user with the `administrator` role. Can edit Drafts, assign fabrics, publish, and archive models. |
| **Client** | A user with the `client` role. Can upload inspiration images and browse Published models. |
| **Completeness gate** | The validation check enforced at publish time: a model must have ≥ 1 critical zone and ≥ 1 compatible fabric. |

---

## Requirements

### Requirement 1: Submit Inspiration Image and AI Draft Generation

**User Story:** As a client, I want to upload an inspiration image of a garment, so that the system can automatically generate a Draft profile with the garment type, cut type, and critical zones pre-filled.

#### Acceptance Criteria

1. WHEN a client submits a valid inspiration image (JPEG, PNG, or WebP; maximum 10 MB) via `POST /models/init`, THE System SHALL synchronously invoke the AI Analyzer, create a MODEL row with `status = Draft`, `version = 1`, `creator_id` set to the authenticated user's ID, `photo_url` pointing to the stored image in Supabase Storage, and pre-fill `garment_type`, `cut_type`, and the associated `MODEL_CRITICAL_ZONE` entries from the AI response, then return HTTP 201 with the Draft profile.
2. IF the AI Analyzer returns a confidence score below 0.70 (on a 0.0–1.0 scale) for the submitted image, THE System SHALL return HTTP 422 with an error message indicating that the image is not recognizable and requesting that the client submit a clearer image, and SHALL NOT create a MODEL row.
3. IF the AI Analyzer is unreachable or returns an unexpected error, THE System SHALL return HTTP 503 with a descriptive error message and SHALL NOT create a MODEL row.
4. IF the authenticated user does not have the `client` role, THE System SHALL return HTTP 403 and SHALL NOT process the image.
5. IF the submitted file is not a valid image format (JPEG, PNG, or WebP), THE System SHALL return HTTP 422 with a format validation error before invoking the AI Analyzer.
6. IF the submitted file exceeds 10 MB, THE System SHALL return HTTP 422 before invoking the AI Analyzer and SHALL NOT create a MODEL row.
7. IF the Supabase Storage upload fails, THE System SHALL return HTTP 500 with a descriptive error message and SHALL NOT create a MODEL row.
8. WHEN the Draft is created, THE System SHALL set `model_name` to `[garment_type] #[N]` (where N is a sequential integer per garment type), which an administrator can later rename.

#### Correctness Properties

- **P1.1 — Draft isolation:** For any MODEL row created by this endpoint, `status` SHALL be `Draft` and `version` SHALL be `1`.
- **P1.2 — No draft on AI failure:** IF the AI Analyzer returns a confidence score below 0.70 for any input image, no MODEL row SHALL exist in the database after the request completes.
- **P1.3 — Client-only invariant:** For any successful call to `POST /models/init`, the `creator_id` SHALL reference a user with `role = client`.
- **P1.4 — Photo persistence:** After a successful Draft creation, the `photo_url` field SHALL contain a non-empty, valid URL string pointing to the Supabase Storage resource, and the image SHALL be retrievable at that URL.

---

### Requirement 2: View Model Catalog

**User Story:** As a client, I want to browse the catalog of Published garment models, so that I can explore available patterns before starting my order.

#### Acceptance Criteria

1. WHEN an authenticated client requests `GET /models`, THE System SHALL return only MODEL rows with `status = Published`, ordered by `model_name` ascending with `model_id` as a tie-breaker, up to a maximum of 100 items, and include a `total` field reflecting the total count of Published models.
2. THE System SHALL include at minimum the following fields in each list item: `model_id`, `model_name`, `garment_type`, `cut_type`, `version`, and `photo_url`.
3. THE System SHALL exclude models with `status = Draft` or `status = Archived` from all client-facing list responses.
4. WHEN no Published models exist, THE System SHALL return HTTP 200 with an empty list and `total = 0`.
5. WHEN an authenticated client requests `GET /models?garment_type={value}`, THE System SHALL return only Published models whose `garment_type` matches the provided value, applying the same ordering and `total` count rules as criterion 1.
6. IF a client filters by a `garment_type` value that is not in the enum (`Dress`, `Shirt`, `Blouse`, `Trousers`, `Skirt`, `Jacket`, `Coat`, `Shorts`, `Suit`, `Traditional`), THE System SHALL return HTTP 422 with a validation error.
7. IF the request does not carry a valid authenticated session, THE System SHALL return HTTP 401.

#### Correctness Properties

- **P2.1 — Completeness:** For every MODEL row with `status = Published`, it SHALL appear in the unfiltered client catalog listing (within the 100-item cap).
- **P2.2 — Exclusion invariant:** No MODEL row with `status = Draft` or `status = Archived` SHALL appear in any client-facing catalog listing response.
- **P2.3 — Filter soundness:** For any `garment_type` filter value G, every model returned SHALL have `garment_type` equal to G.

---

### Requirement 3: View Model Detail

**User Story:** As a client, I want to view the full profile of a Published model, so that I can understand its cut constraints and compatible fabrics before choosing it.

#### Acceptance Criteria

1. WHEN an authenticated client requests `GET /models/{model_id}` for a Published model, THE System SHALL return: `model_id`, `model_name`, `description`, `garment_type`, `cut_type`, `status`, `version`, `photo_url`, a `zones` list where each entry includes `zone_id` and `zone_name`, and a `fabrics` list where each entry includes `fabric_id` and `fabric_name`. The response SHALL NOT include `creator_id`.
2. IF the requested `model_id` does not exist, THE System SHALL return HTTP 404 with an error message indicating the model was not found.
3. IF the requested model has `status = Archived`, THE System SHALL return HTTP 404 (treat as non-existent for clients).
4. IF the requested model has `status = Draft`, THE System SHALL return HTTP 404 (Draft profiles are not visible to clients).
5. IF the `model_id` path parameter is not a valid UUID, THE System SHALL return HTTP 422.
6. IF the request does not carry a valid authenticated session, THE System SHALL return HTTP 401.

#### Correctness Properties

- **P3.1 — Published visibility:** For any model with `status = Published`, a client detail request SHALL return HTTP 200 with the full profile.
- **P3.2 — Non-published invisibility:** For any model with `status = Draft` or `status = Archived`, a client detail request SHALL return HTTP 404.
- **P3.3 — Zone and fabric completeness:** The zones and fabrics lists returned in a Published model detail SHALL contain at least one entry each (enforced by the completeness gate at publish time).

---

### Requirement 4: Administrator Reviews and Edits a Draft

**User Story:** As an administrator, I want to review and correct the AI-generated Draft profile fields, so that the model's garment type, cut type, name, description, and critical zones are accurate before publication.

#### Acceptance Criteria

1. WHEN an administrator sends `PATCH /models/{model_id}` for a model with `status = Draft`, THE System SHALL apply only the fields present in the request body (omitted fields remain unchanged), enforce all field-level validations, and return HTTP 200 with the complete updated Draft.
2. THE System SHALL accept and validate the following editable fields on a Draft: `model_name` (1–100 non-whitespace characters after trimming), `description` (optional text, maximum 1000 characters), `garment_type` (must be a valid enum value), `cut_type` (must be one of `Fitted`, `Semi-fitted`, `Loose`).
3. IF an administrator provides a `garment_type` value not in the enum (`Dress`, `Shirt`, `Blouse`, `Trousers`, `Skirt`, `Jacket`, `Coat`, `Shorts`, `Suit`, `Traditional`), THE System SHALL return HTTP 422.
4. IF an administrator provides a `cut_type` value not in (`Fitted`, `Semi-fitted`, `Loose`), THE System SHALL return HTTP 422.
5. IF an administrator provides a `model_name` that is empty, whitespace-only, or exceeds 100 characters after trimming, THE System SHALL return HTTP 422.
6. IF the target model does not exist, THE System SHALL return HTTP 404.
7. IF the target model has `status = Published` or `status = Archived`, THE System SHALL return HTTP 409 indicating that the model is not in Draft status.
8. IF the request does not carry the `administrator` role claim, THE System SHALL return HTTP 403 and make no changes.
9. WHEN an administrator assigns critical zones to a Draft via `PUT /models/{model_id}/zones`, THE System SHALL replace the current `MODEL_CRITICAL_ZONE` entries for that model with the provided zone IDs and return HTTP 200 with the updated zone list.
10. IF a provided `zone_id` does not exist in the `CRITICAL_ZONE` table, THE System SHALL return HTTP 422 and make no changes.
11. IF the zone assignment list is empty, THE System SHALL accept it and clear all zones, allowing the administrator to start a fresh assignment.

#### Correctness Properties

- **P4.1 — Role enforcement:** For any PATCH or PUT request to a Draft model without a valid `administrator` role, the system SHALL return 403 and the database SHALL remain unchanged.
- **P4.2 — Enum invariant:** No MODEL row SHALL have a `garment_type` value outside the ten-value enum or a `cut_type` value outside (`Fitted`, `Semi-fitted`, `Loose`).
- **P4.3 — Name length invariant:** No persisted MODEL row SHALL have a `model_name` longer than 100 characters, an empty `model_name`, or a whitespace-only `model_name`.
- **P4.4 — Zone referential integrity:** No `MODEL_CRITICAL_ZONE` entry SHALL reference a `zone_id` that does not exist in the `CRITICAL_ZONE` table.

---

### Requirement 5: Assign Compatible Fabrics to a Model

**User Story:** As an administrator, I want to assign compatible fabrics from the Fabric Catalog to a model, so that the Compatibility Engine knows which fabrics are suitable for this garment pattern.

#### Acceptance Criteria

1. WHEN an administrator sends `PUT /models/{model_id}/fabrics` with a list of `fabric_id` values, THE System SHALL verify that each `fabric_id` exists in Module 3 and has `fabric_status = available`, then atomically replace all current `MODEL_FABRIC` entries for that model with the provided list, and return HTTP 200 with the updated fabric list.
2. IF any provided `fabric_id` does not exist in Module 3, THE System SHALL return HTTP 422 with an error identifying the unknown fabric ID and make no changes to the model.
3. IF any provided `fabric_id` exists in Module 3 but has `fabric_status != available` (unavailable or archived), THE System SHALL return HTTP 422 with an error identifying the fabric and make no changes.
4. IF the fabric list is empty, THE System SHALL accept it and remove all `MODEL_FABRIC` entries for the model; the model will fail the completeness gate and cannot be published until at least one fabric is re-assigned.
5. IF the request does not carry the `administrator` role claim, THE System SHALL return HTTP 403.
6. IF the target `model_id` does not exist, THE System SHALL return HTTP 404.
7. WHILE a model has `status = Published`, WHEN an administrator reassigns fabrics, THE System SHALL apply the same validation rules and update the `MODEL_FABRIC` entries; THE System SHALL NOT increment `version` or create a snapshot until a `POST /models/{model_id}/publish` action is explicitly submitted.
8. IF the provided `fabric_id` list contains duplicate values, THE System SHALL deduplicate them and persist only unique entries.

#### Correctness Properties

- **P5.1 — Availability invariant:** No `MODEL_FABRIC` entry SHALL reference a `fabric_id` whose `fabric_status` in Module 3 is not `available` at the time of assignment.
- **P5.2 — Referential integrity:** No `MODEL_FABRIC` entry SHALL reference a `fabric_id` that does not exist in Module 3.
- **P5.3 — Role enforcement:** For any fabric assignment request without a valid `administrator` role, the system SHALL return 403 and the `MODEL_FABRIC` table SHALL remain unchanged.

---

### Requirement 6: Publish a Model

**User Story:** As an administrator, I want to publish a Draft model after reviewing it, so that it becomes visible to clients and usable by the Compatibility Engine.

#### Acceptance Criteria

1. WHEN an administrator sends `POST /models/{model_id}/publish` for a model with `status = Draft`, THE System SHALL verify the completeness gate before making any state change, transition the model to `status = Published`, and return HTTP 200 with the full published model.
2. IF the model has zero `MODEL_CRITICAL_ZONE` entries at publish time, THE System SHALL return HTTP 422 with an error message indicating that at least one critical zone is required.
3. IF the model has zero `MODEL_FABRIC` entries at publish time, THE System SHALL return HTTP 422 with an error message indicating that at least one compatible fabric is required.
4. IF the model has both zero `MODEL_CRITICAL_ZONE` entries and zero `MODEL_FABRIC` entries at publish time, THE System SHALL return HTTP 422 with an error message indicating both missing critical zones and missing fabrics.
5. IF the target model does not exist, THE System SHALL return HTTP 404.
6. IF the request does not carry the `administrator` role claim, THE System SHALL return HTTP 403.
7. IF the model already has `status = Published`, THE System SHALL return HTTP 409 indicating the model is already published.
8. IF the model has `status = Archived`, THE System SHALL return HTTP 409 indicating the model cannot be published from Archived status.

#### Correctness Properties

- **P6.1 — Completeness gate invariant:** No MODEL row with `status = Published` SHALL have zero `MODEL_CRITICAL_ZONE` entries. No MODEL row with `status = Published` SHALL have zero `MODEL_FABRIC` entries.
- **P6.2 — Transition atomicity:** IF the completeness gate check fails, the MODEL row `status` SHALL remain `Draft` and no side-effects SHALL occur.
- **P6.3 — No unauthorized publish:** For any publish request without a valid `administrator` role, the model `status` SHALL remain unchanged.

---

### Requirement 7: Edit a Published Model with Snapshotting

**User Story:** As an administrator, I want to edit and republish a Published model while preserving the previous version immutably, so that historical reports always reflect the exact profile that was used when they were generated.

#### Acceptance Criteria

1. WHEN an administrator sends `PATCH /models/{model_id}` for a model with `status = Published`, THE System SHALL, within a single database transaction: (a) write a complete snapshot of the current MODEL row and its `MODEL_CRITICAL_ZONE` and `MODEL_FABRIC` relations to the `MODEL_SNAPSHOT` table, then (b) apply the field updates to the live MODEL row, and return HTTP 200 with the updated model.
2. IF the snapshot write fails for any reason, THE System SHALL roll back the entire transaction and return HTTP 500, leaving the live MODEL row and `MODEL_SNAPSHOT` table unchanged.
3. WHEN an administrator sends `POST /models/{model_id}/publish` for a model with `status = Published`, THE System SHALL verify the completeness gate, increment `version` by 1 on the live MODEL row, and return HTTP 200 with the updated model.
4. WHEN the completeness gate fails at republish, THE System SHALL return HTTP 422 with an error message identifying the missing component (critical zone, fabric, or both), and the `version` SHALL NOT be incremented.
5. THE System SHALL accept the same editable fields as in Requirement 4 on a Published model: `model_name`, `description`, `garment_type`, and `cut_type`.
6. IF `PATCH /models/{model_id}` is sent for a model with `status != Published`, THE System SHALL return HTTP 409 redirecting the caller to Requirement 4 for Draft editing or indicating the model is Archived.
7. IF the request does not carry the `administrator` role claim, THE System SHALL return HTTP 403.
8. THE snapshot stored in `MODEL_SNAPSHOT` SHALL contain: `model_id`, `snapshot_version` (the version number at the time of the snapshot), `model_name`, `description`, `garment_type`, `cut_type`, `photo_url`, `status`, `creator_id`, a copy of all `MODEL_CRITICAL_ZONE` entries, and a copy of all `MODEL_FABRIC` entries associated with the model at the time of the snapshot.
9. WHEN the completeness gate passes at republish, THE System SHALL NOT create an additional snapshot; the snapshot is created only on the PATCH (edit) operation, not on the publish operation.

#### Correctness Properties

- **P7.1 — Snapshot-before-update invariant:** For any PATCH cycle on a Published model, a `MODEL_SNAPSHOT` row capturing the state immediately before the update SHALL exist upon completion of the transaction.
- **P7.2 — Version monotonicity:** The `version` field on any MODEL row SHALL strictly increase with each republish cycle; it SHALL never decrease.
- **P7.3 — Snapshot fidelity (round-trip):** For any `MODEL_SNAPSHOT` row, reconstructing a profile from the snapshot's field values, zones, and fabrics SHALL produce a state identical to the live model at the `snapshot_version` recorded in the snapshot.
- **P7.4 — Atomicity under failure:** IF a snapshot write is injected to fail (simulated fault), the live MODEL row SHALL remain unchanged and no partial `MODEL_SNAPSHOT` row SHALL exist.

---

### Requirement 8: Archive a Model

**User Story:** As an administrator, I want to archive a Draft or Published model, so that it is removed from the active catalog while historical data remains accessible for past reports.

#### Acceptance Criteria

1. WHEN an administrator sends `POST /models/{model_id}/archive` for a model with `status = Draft` or `status = Published`, THE System SHALL transition the model's `status` to `Archived` and return HTTP 200.
2. WHILE a model has `status = Archived`, THE System SHALL exclude it from all `GET /models` list responses (the archived model SHALL NOT appear in the listing).
3. WHILE a model has `status = Archived`, THE System SHALL return HTTP 404 for `GET /models/{model_id}` requests from clients.
4. WHILE a model has `status = Archived`, THE System SHALL return HTTP 200 with the model's full data — including all fields, zones (`zone_id`, `zone_name`), and fabrics (`fabric_id`, `fabric_name`) — for `GET /models/{model_id}/constraints` requests from downstream modules.
5. IF the target model does not exist, THE System SHALL return HTTP 404.
6. IF the model already has `status = Archived`, THE System SHALL return HTTP 409 and make no changes.
7. IF the request does not carry the `administrator` role claim, THE System SHALL return HTTP 403.
8. IF the archive operation fails due to a database error after the status update has been initiated, THE System SHALL return HTTP 500 and the model `status` SHALL revert to its pre-archive value.

#### Correctness Properties

- **P8.1 — Client invisibility after archive:** For any model transitioned to `status = Archived`, subsequent client-facing `GET /models` listings SHALL not include it, and `GET /models/{model_id}` SHALL return HTTP 404.
- **P8.2 — Internal data preservation:** For any archived model, the internal constraints endpoint SHALL return HTTP 200 with complete data; no fields SHALL be nullified or removed by the archive operation.
- **P8.3 — Idempotency guard:** Archiving an already-Archived model SHALL return HTTP 409; the model SHALL not be modified.

---

### Requirement 9: Expose Model Constraints to Downstream Modules

**User Story:** As Module 6 (Compatibility Engine) or Module 7 (Report), I want to retrieve the full constraints of a model by its ID, so that I can perform compatibility checks and generate accurate reports for any model version, including archived ones.

#### Acceptance Criteria

1. WHEN a downstream module requests `GET /models/{model_id}/constraints` for a model with `status = Published` or `status = Archived`, THE System SHALL return: `model_id`, `model_name`, `version`, `garment_type`, `cut_type`, a `zones` list where each entry includes `zone_id` and `zone_name`, and a `fabrics` list where each entry includes `fabric_id` and `fabric_name`.
2. WHEN the requested model has `status = Archived`, THE System SHALL return HTTP 200 with the full model constraints (archived models must remain accessible for historical report reconstruction).
3. IF the requested model has `status = Draft`, THE System SHALL return HTTP 404; Draft profiles are not yet complete and SHALL NOT be consulted by downstream modules.
4. IF the requested `model_id` does not exist, THE System SHALL return HTTP 404.
5. THE System SHALL make this endpoint accessible to any authenticated request (any valid role or internal service token); it is not restricted to the `administrator` role.
6. IF the `model_id` path parameter is not a valid UUID, THE System SHALL return HTTP 422.
7. IF the request does not carry any valid authentication credential, THE System SHALL return HTTP 401.

#### Correctness Properties

- **P9.1 — Data accuracy invariant:** For any Published or Archived model, the `cut_type`, `garment_type`, `version`, zones, and fabrics returned by the constraints endpoint SHALL exactly match the stored values in the MODEL, `MODEL_CRITICAL_ZONE`, and `MODEL_FABRIC` tables.
- **P9.2 — Archived accessibility:** For every model with `status = Archived`, the constraints endpoint SHALL return HTTP 200; this endpoint SHALL never return HTTP 404 for an Archived model.
- **P9.3 — Draft exclusion:** For every model with `status = Draft`, the constraints endpoint SHALL return HTTP 404.
- **P9.4 — Version consistency:** The `version` value returned in the constraints response SHALL always match the `version` field of the live MODEL row for the given `model_id`.
