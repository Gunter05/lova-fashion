# Requirements Document

## Introduction

The Fabric Catalog module manages the reference catalog of available fabrics and fabric
categories for the Lova Fashion custom-fit application. It exposes technical properties
(elasticity rate, rigidity level) to the Ease Margin Calculation Engine and the
Compatibility Verification Engine, and allows clients to browse and select fabrics while
giving catalog managers full CRUD control over catalog content.

This module is part of the `auth_catalogues` module group and is a standalone
reference-data service with no dependency on other modules. It only assumes that an
already-validated JWT with a `role` claim is present on incoming requests; JWT validation
and user management are handled by Module 1 (Authentication).

---

## Glossary

| Term | Definition |
|---|---|
| **Fabric** | A specific textile reference available in the catalog (e.g. Wax Vlisco ref. 1234). |
| **Fabric category** | A family of fabrics sharing similar properties (e.g. Wax, Jersey, Denim). |
| **Elasticity rate** | A measure of a fabric's ability to stretch, expressed as a percentage (0–100 %). Used by the Ease Margin Calculation Engine. |
| **Rigidity level** | A qualitative descriptor of how rigid a fabric type is (`rigid`, `semi-stretch`, `stretch`). Defined at the category level. |
| **Ease margin** | Extra space added to measurements to ensure garment comfort; calculated by Module 5 using data from this catalog. |
| **Catalog manager** | A user with the `catalog_manager` role who can create, update, and remove catalog entries. |
| **Client** | A user with the `client` role who can browse and select fabrics. |
| **Archived fabric** | A fabric that has been soft-deleted; kept in the database for historical reference but hidden from all client-facing queries. |

---

## Requirements

### Requirement 1: Browse Fabrics by Category

**User Story:** As a client, I want to browse available fabrics grouped by category, so that I can explore options before choosing one for my garment.

#### Acceptance Criteria

1. WHEN a client requests the list of fabrics, THE SYSTEM SHALL return only fabrics whose `fabric_status` is `available`, grouped by their associated category.
2. WHEN a client filters by a specific category ID, THE SYSTEM SHALL return only `available` fabrics belonging to that category.
3. THE SYSTEM SHALL exclude fabrics with `fabric_status` of `unavailable` or `archived` from all client-facing list responses.
4. WHEN no fabrics exist in a valid category, THE SYSTEM SHALL return an empty list for that category without an error.
5. THE SYSTEM SHALL include at minimum the following fields in each list item: `fabric_id`, `fabric_name`, `fabric_unit_price`, `fabric_photo`, `fabric_status`, and the parent `category_name`.
6. IF a client filters by a `category_id` that does not exist, THE SYSTEM SHALL return HTTP 404 with an error message indicating the category was not found.

#### Correctness Properties

- **P1.1 — Completeness:** For every fabric in the database with `fabric_status = available`, it SHALL appear in the unfiltered client listing.
- **P1.2 — Exclusion:** For every fabric with `fabric_status` of `unavailable` or `archived`, it SHALL NOT appear in any client-facing listing response.
- **P1.3 — Category filter soundness:** For any category filter value C, every fabric returned SHALL have `category_id` matching C.

---

### Requirement 2: View Fabric Detail

**User Story:** As a client, I want to view the full technical properties of a fabric, so that I can make an informed selection based on elasticity, weight, composition, and price.

#### Acceptance Criteria

1. WHEN a client requests a fabric by its `fabric_id`, THE SYSTEM SHALL return all fabric attributes: `fabric_id`, `fabric_name`, `fabric_elasticity_rate`, `fabric_weight`, `fabric_composition`, `fabric_unit_price`, `fabric_photo`, `fabric_status`, `category_id`, and the parent category's `category_name` and `reference_rigidity_level`.
2. IF a client requests a fabric that does not exist, THE SYSTEM SHALL return HTTP 404 with an error message indicating that the requested fabric was not found.
3. IF a client requests a fabric whose `fabric_status` is `archived`, THE SYSTEM SHALL return HTTP 404 (treat as non-existent for clients).
4. WHEN a client requests a fabric whose `fabric_status` is `unavailable`, THE SYSTEM SHALL return HTTP 200 with the full fabric detail where the `fabric_status` field is set to `unavailable`, and the response SHALL NOT include a selection confirmation option.

#### Correctness Properties

- **P2.1 — Data integrity:** The `reference_rigidity_level` returned in a fabric detail response SHALL always match the rigidity level of the fabric's parent category.
- **P2.2 — Archived invisibility:** For any archived fabric ID, a client-facing detail request SHALL return 404.

---

### Requirement 3: Select a Fabric for an Order

**User Story:** As a client, I want to select a fabric for my garment, so that it can be passed to the measurement and compatibility modules.

#### Acceptance Criteria

1. WHEN a client selects a fabric with `fabric_status = available`, THE SYSTEM SHALL return HTTP 200 confirming the selection with the fabric's `fabric_id`, `fabric_elasticity_rate`, and the category's `reference_rigidity_level`.
2. IF a client attempts to select a fabric with `fabric_status = unavailable`, THE SYSTEM SHALL return HTTP 409 and include in the response up to 3 alternative fabrics from the same category that have `fabric_status = available`, sorted by `fabric_name` ascending, excluding the rejected fabric.
3. IF a client attempts to select a fabric with `fabric_status = archived`, THE SYSTEM SHALL return HTTP 404.
4. IF a client attempts to select a fabric that does not exist, THE SYSTEM SHALL return HTTP 404.
5. IF no alternative available fabrics exist in the same category, THE SYSTEM SHALL return the 409 response with an empty alternatives list.
6. IF the `fabric_id` provided in the selection request is malformed (not a valid UUID), THE SYSTEM SHALL return HTTP 422.

#### Correctness Properties

- **P3.1 — No unavailable selection:** It SHALL be impossible for the system to confirm a selection of a fabric with `fabric_status != available`.
- **P3.2 — Alternatives validity:** Every fabric returned as an alternative SHALL have `fabric_status = available` and the same `category_id` as the rejected fabric.
- **P3.3 — Alternatives count:** The number of alternatives returned SHALL be at most 3 and SHALL NOT include the rejected fabric itself.

---

### Requirement 4: Manage Fabric Categories

**User Story:** As a catalog manager, I want to add, edit, and remove fabric categories, so that I can keep the catalog organized and up to date.

#### Acceptance Criteria

1. WHEN a catalog manager creates a category with a valid `category_name` (1–50 non-empty characters) and a valid `reference_rigidity_level`, THE SYSTEM SHALL persist the new category and return HTTP 201 with the new category including its generated `category_id`.
2. IF a catalog manager attempts to create a category with a `category_name` that is empty or exceeds 50 characters, THE SYSTEM SHALL return HTTP 422 with a validation error.
3. IF a catalog manager attempts to create a category with an invalid `reference_rigidity_level` (not one of `rigid`, `semi-stretch`, `stretch`), THE SYSTEM SHALL return HTTP 422.
4. WHEN a catalog manager updates an existing category, THE SYSTEM SHALL apply only the provided fields, enforce that `category_name` (if provided) remains 1–50 characters and `reference_rigidity_level` (if provided) is a valid enum value, and return the updated category.
5. IF a catalog manager attempts to update a category that does not exist, THE SYSTEM SHALL return HTTP 404.
6. WHEN a catalog manager deletes a category that has no associated fabrics, THE SYSTEM SHALL permanently delete the category and return HTTP 204.
7. IF a catalog manager attempts to delete a category that still has associated fabrics, THE SYSTEM SHALL return HTTP 409 and prevent deletion.
8. WHERE the request does not carry a `catalog_manager` role claim, THE SYSTEM SHALL return HTTP 403 for all category mutation endpoints (POST, PATCH, DELETE).

#### Correctness Properties

- **P4.1 — Role enforcement:** For any category create/update/delete request without a valid `catalog_manager` role, the system SHALL return 403 and make no changes to the database.
- **P4.2 — Orphan prevention:** Deleting a category with associated fabrics SHALL always be rejected.
- **P4.3 — Name length invariant:** No persisted category SHALL have a `category_name` longer than 50 characters.

---

### Requirement 5: Manage Fabric References

**User Story:** As a catalog manager, I want to add, edit, and remove fabric references, so that clients always have an accurate and current catalog to choose from.

#### Acceptance Criteria

1. WHEN a catalog manager creates a fabric with valid attributes (including `fabric_name` of 1–100 characters, `fabric_elasticity_rate` in [0, 100], `fabric_unit_price` > 0, `fabric_weight` > 0) and a valid existing `category_id`, THE SYSTEM SHALL persist the new fabric with `fabric_status = available` by default and return HTTP 201 with the fabric including its generated `fabric_id`.
2. IF a catalog manager attempts to create a fabric without specifying a `category_id`, THE SYSTEM SHALL return HTTP 422 and block creation.
3. IF a catalog manager attempts to create a fabric with a `category_id` that does not reference an existing category, THE SYSTEM SHALL return HTTP 422.
4. IF a catalog manager attempts to create a fabric with `fabric_elasticity_rate` outside the range [0, 100], THE SYSTEM SHALL return HTTP 422.
5. IF a catalog manager attempts to create a fabric with `fabric_unit_price` ≤ 0, THE SYSTEM SHALL return HTTP 422.
6. IF a catalog manager attempts to create a fabric with `fabric_weight` ≤ 0, THE SYSTEM SHALL return HTTP 422.
7. WHEN a catalog manager updates an existing fabric, THE SYSTEM SHALL apply only the provided fields, enforce all business rule constraints on the updated values (elasticity, price, weight, category existence, name length), and return the updated fabric.
8. IF a catalog manager attempts to update a fabric that does not exist, THE SYSTEM SHALL return HTTP 404.
9. WHEN a catalog manager sets a fabric's status to `unavailable`, THE SYSTEM SHALL update `fabric_status` to `unavailable`; the fabric SHALL no longer appear in client listing or selection responses.
10. WHEN a catalog manager sets a fabric's status to `archived`, THE SYSTEM SHALL update `fabric_status` to `archived`; the fabric SHALL be excluded from all client-facing list, detail, and selection responses but SHALL remain in the database.
11. IF a catalog manager attempts to set `fabric_status` to a value other than `available`, `unavailable`, or `archived`, THE SYSTEM SHALL return HTTP 422.
12. WHERE the request does not carry a `catalog_manager` role claim, THE SYSTEM SHALL return HTTP 403 for all fabric mutation endpoints (POST, PATCH, DELETE).

#### Correctness Properties

- **P5.1 — Elasticity range invariant:** No persisted fabric SHALL have `fabric_elasticity_rate` outside [0, 100].
- **P5.2 — Price positivity invariant:** No persisted fabric SHALL have `fabric_unit_price` ≤ 0.
- **P5.3 — Category membership invariant:** No persisted fabric SHALL have a `category_id` that does not reference an existing FABRIC_CATEGORY row.
- **P5.4 — Default status:** Every newly created fabric SHALL have `fabric_status = available` unless explicitly overridden.

---

### Requirement 6: Upload Fabric Photo

**User Story:** As a catalog manager, I want to upload a photo for a fabric, so that clients can see what the fabric looks like before making a selection.

#### Acceptance Criteria

1. WHEN a catalog manager uploads a valid image file to `POST /fabrics/{fabric_id}/photo`, THE SYSTEM SHALL store the file in Supabase Storage, update `fabric_photo` with the returned public URL, and return the updated fabric record.
2. WHEN a catalog manager uploads a photo for a fabric that does not exist, THE SYSTEM SHALL return HTTP 404.
3. WHEN the Supabase Storage upload fails, THE SYSTEM SHALL return HTTP 500 with a descriptive error message and SHALL NOT update `fabric_photo`.
4. WHERE the request does not carry a `catalog_manager` role claim, THE SYSTEM SHALL return HTTP 403.
5. WHEN a catalog manager replaces an existing photo, THE SYSTEM SHALL overwrite the `fabric_photo` URL with the new one.

#### Correctness Properties

- **P6.1 — Atomicity:** If the Supabase Storage upload fails, the `fabric_photo` field SHALL remain unchanged.
- **P6.2 — URL validity:** After a successful upload, `fabric_photo` SHALL contain a non-empty, valid URL string pointing to the Supabase Storage resource.

---

### Requirement 7: Expose Technical Properties to Downstream Modules

**User Story:** As the Ease Margin Calculation Engine or Compatibility Verification Engine, I want to retrieve a fabric's technical properties by its ID, so that I can compute ease margins and check compatibility accurately.

#### Acceptance Criteria

1. WHEN a downstream module requests technical properties for a valid `fabric_id`, THE SYSTEM SHALL return `fabric_id`, `fabric_elasticity_rate`, `category_id`, and the category's `reference_rigidity_level`.
2. WHEN a downstream module requests properties for a `fabric_id` that does not exist, THE SYSTEM SHALL return HTTP 404.
3. THE SYSTEM SHALL expose these properties via a dedicated internal endpoint (e.g. `GET /fabrics/{fabric_id}/properties`) accessible with a service-level token or any authenticated role.
4. WHEN a fabric has `fabric_status = archived`, THE SYSTEM SHALL still return its technical properties to downstream modules (historical orders may reference archived fabrics).

#### Correctness Properties

- **P7.1 — Elasticity accuracy:** The `fabric_elasticity_rate` returned by the internal properties endpoint SHALL exactly match the stored value in the database for the given `fabric_id`.
- **P7.2 — Rigidity source:** The `reference_rigidity_level` returned SHALL always originate from the fabric's parent FABRIC_CATEGORY record.
