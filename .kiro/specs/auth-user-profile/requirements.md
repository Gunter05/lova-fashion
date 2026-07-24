# Requirements Document

## Introduction

This document specifies the requirements for **Module 1: Authentication & User Profile** of the Lova Fashion application — a remote custom-fit styling platform for Cameroon (AWS re:Deploy 2026, Fashion theme).

The module is the identity backbone of the entire system. It handles user registration, authentication, secure session management, role-based access control, personal profile management (including profile picture history in Supabase Storage), and the longitudinal store of raw body measurements. It acts as the identity provider for all other modules, emitting `user.authenticated` system-wide and `user.profile_data` to Module 5, while receiving `measurements.estimated` from Module 2 and `report.saved` from Module 7.

---

## Glossary

- **Auth_Service**: The authentication sub-system responsible for credential validation, JWT issuance, and session lifecycle management.
- **User**: A person registered on the Lova Fashion platform holding an active account, uniquely identified by CNI and email.
- **Client**: A User with the `Client` role who books styling sessions and consults results.
- **Tailor**: A User with the `Tailor` role who manages garment recommendations and interacts with measurement data.
- **Admin**: A User with the `Admin` role who manages users and platform catalogs.
- **CNI**: National Identity Card number — the primary unique business key for a User. Format: exactly 9 alphanumeric characters.
- **JWT**: JSON Web Token issued upon successful authentication to authorize subsequent requests.
- **Profile_Service**: The sub-system managing personal profile data, profile pictures, and measurement history.
- **PhotoProfil**: An image uploaded by or on behalf of a User and stored in Supabase Storage, representing a profile picture at a point in time.
- **Mensuration**: A complete set of raw body measurements (chest, waist, hips, arm length, height) recorded for a User on a specific date.
- **Measurement_Service**: The sub-system responsible for receiving, validating, and persisting Mensuration entries.
- **Module_2**: The Photo Capture & Measurement Estimation module that produces `measurements.estimated` events.
- **Module_5**: The Ease Margin Calculation Engine that consumes `user.profile_data`.
- **Module_7**: The Final Result & Report module that produces `report.saved` events.
- **Event_Bus**: The internal application event routing mechanism through which inter-module events are published and consumed.
- **Supabase_Storage**: The object storage service used to persist uploaded photos.
- **Role**: An enumeration (`Client` | `Tailor` | `Admin`) attached to each User that governs access permissions across the platform.
- **date_inscription**: The UTC timestamp automatically recorded when a User account is created.
- **date_mensuration**: The UTC timestamp recorded when a Mensuration entry is created.
- **date_upload**: The UTC timestamp recorded when a PhotoProfil is stored.
- **is_active**: A boolean flag on the User record; `true` by default, set to `false` when an Admin deactivates the account.

---

## Requirements

### Requirement 1: User Registration

**User Story:** As a new user (Client, Tailor, or Admin), I want to register an account with my national ID, name, email, password, and role, so that I can access the Lova Fashion platform with a personalised identity.

#### Acceptance Criteria

1. WHEN a registration request is submitted with CNI, nom, email, mot_de_passe, and role, and all fields pass validation, THE Auth_Service SHALL create a new User record with `is_active` set to `true`, store mot_de_passe as a bcrypt hash, set date_inscription to the current UTC timestamp, and return an HTTP 201 response containing the new User's CNI, nom, email, role, and date_inscription.
2. IF the submitted CNI already exists in the system, THEN THE Auth_Service SHALL reject the registration request with HTTP 409 and return an error body identifying the `cni` field as the source of the conflict.
3. IF the submitted email already exists in the system, THEN THE Auth_Service SHALL reject the registration request with HTTP 409 and return an error body identifying the `email` field as the source of the conflict.
4. IF a registration request omits any required field (CNI, nom, email, mot_de_passe, role), THEN THE Auth_Service SHALL reject the request with HTTP 422 and return a validation error body identifying each missing field.
5. IF a registration request provides an invalid role value (i.e., not one of `Client`, `Tailor`, `Admin`), THEN THE Auth_Service SHALL reject the request with HTTP 422 and return a validation error listing the three accepted values.
6. IF a registration request provides a CNI that is not exactly 9 alphanumeric characters, THEN THE Auth_Service SHALL reject the request with HTTP 422 and return a validation error specifying the CNI format rule.
7. IF a registration request provides an email that does not match the standard email format (local-part@domain.tld), THEN THE Auth_Service SHALL reject the request with HTTP 422 and return a validation error specifying the email field.
8. IF a registration request provides a mot_de_passe shorter than 8 characters, THEN THE Auth_Service SHALL reject the request with HTTP 422 and return a validation error specifying the minimum password length.
9. IF a registration request provides a nom exceeding 100 characters, THEN THE Auth_Service SHALL reject the request with HTTP 422 and return a validation error specifying the maximum name length.
10. WHEN a User is successfully created, THE Auth_Service SHALL NOT persist the plaintext mot_de_passe at any point during or after the request lifecycle.

---

### Requirement 2: User Authentication (Login)

**User Story:** As a registered user, I want to log in with my email and password, so that I receive a JWT that grants me access to the platform's features.

#### Acceptance Criteria

1. WHEN a login request is submitted with a valid email and matching mot_de_passe for an active User, THE Auth_Service SHALL issue a signed JWT containing the User's CNI, role, and expiry timestamp as claims.
2. WHEN a JWT is issued, THE Auth_Service SHALL set the token expiry claim to exactly 24 hours from the issuance time.
3. IF the submitted email does not correspond to any User, THEN THE Auth_Service SHALL return HTTP 401 with a generic error message that does not disclose whether the email or the password is the source of the failure.
4. IF the submitted mot_de_passe does not match the stored hash for the given email, THEN THE Auth_Service SHALL return HTTP 401 with the same generic error message as criterion 3.
5. WHEN authentication succeeds, THE Auth_Service SHALL publish a `user.authenticated` event to the Event_Bus containing the User's CNI, role, and the authentication timestamp.
6. IF a login request omits the email or mot_de_passe field, THEN THE Auth_Service SHALL return HTTP 422 and a validation error identifying each missing field, without attempting credential lookup.
7. IF a User has submitted 5 or more consecutive failed login attempts within a 15-minute window, THEN THE Auth_Service SHALL reject further login attempts for that User with HTTP 429 and an error indicating temporary lockout, until the window expires.
8. IF the Event_Bus is unavailable when authentication succeeds, THEN THE Auth_Service SHALL still issue the JWT and log the event publication failure, without blocking the login response.

---

### Requirement 3: User Logout and Session Termination

**User Story:** As an authenticated user, I want to log out, so that my session is terminated and my JWT can no longer be used.

#### Acceptance Criteria

1. WHEN a logout request is received bearing a valid, non-expired, non-invalidated JWT, THE Auth_Service SHALL add the token's unique identifier (`jti`) to an invalidation store and return HTTP 200 confirming session termination.
2. IF a logout request is received bearing an already-invalidated JWT, THEN THE Auth_Service SHALL return HTTP 200 (idempotent response) without attempting a second invalidation.
3. IF a logout request is received bearing an expired JWT, THEN THE Auth_Service SHALL return HTTP 401 indicating the session has already expired, without adding the token to the invalidation store.
4. IF a logout request is received with no JWT in the Authorization header, THEN THE Auth_Service SHALL return HTTP 401 indicating that authentication credentials are required.
5. IF a request to any protected endpoint is received bearing a JWT whose `jti` is present in the invalidation store, THEN THE Auth_Service SHALL return HTTP 401 and SHALL NOT grant access to the requested resource.

---

### Requirement 4: JWT Validation and Session Enforcement

**User Story:** As the platform, I want every protected endpoint to verify the JWT, so that only authenticated and authorised users can access their data.

#### Acceptance Criteria

1. WHEN a protected endpoint receives a request, THE Auth_Service SHALL extract the JWT from the `Authorization` header as a Bearer token before performing any further validation.
2. WHEN a JWT has been extracted, THE Auth_Service SHALL verify the token signature using the Auth_Service signing key, confirm the `iss` claim matches the Auth_Service issuer identifier, and confirm all required claims (CNI, role, expiry) are present.
3. IF a protected endpoint receives a request with no `Authorization` header or no Bearer token, THEN THE Auth_Service SHALL return HTTP 401 with an error indicating that authentication credentials are required.
4. IF a protected endpoint receives a request with an expired JWT (expiry timestamp in the past), THEN THE Auth_Service SHALL return HTTP 401 with an error message indicating the token has expired.
5. IF a protected endpoint receives a request with a JWT that fails signature verification, has an unrecognised `iss` claim, has invalid structure, or is missing required claims, THEN THE Auth_Service SHALL return HTTP 401 with an error message indicating the token is invalid.
6. WHEN a JWT passes all validation checks, THE Auth_Service SHALL make the authenticated User's CNI and role available to all downstream request handlers within the same request lifecycle.

---

### Requirement 5: Role-Based Access Control

**User Story:** As the platform, I want access to resources to be governed by the authenticated user's role, so that Clients, Tailors, and Admins can only perform actions appropriate to their role.

#### Acceptance Criteria

1. WHILE a User is authenticated with the `Client` role, THE Profile_Service SHALL permit that User to read and update their own profile data, upload profile pictures, and consult their own Mensuration history.
2. WHILE a User is authenticated with the `Tailor` role, THE Profile_Service SHALL permit that User to read their own profile, upload their own profile pictures, and read the Mensuration history of Clients explicitly assigned to them via a confirmed tailor-client assignment record.
3. WHILE a User is authenticated with the `Admin` role, THE Profile_Service SHALL permit that User to read and update any User's profile data and assign or revoke roles for any non-Admin User account.
4. IF a User authenticated with the `Tailor` role attempts to read the Mensuration history of a Client not explicitly assigned to them, THEN THE Profile_Service SHALL return HTTP 403 without exposing any measurement data.
5. IF a User attempts to access or modify another User's profile data without the `Admin` role, THEN THE Profile_Service SHALL return HTTP 403. Access control is enforced entirely at the Profile_Service level; no additional fallback mechanism is provided.
6. IF a User attempts to access an endpoint requiring a role they do not hold, THEN THE Auth_Service SHALL return HTTP 403.

---

### Requirement 6: View and Update Personal Profile

**User Story:** As an authenticated user, I want to view and update my profile information (name, email), so that my account details remain accurate.

#### Acceptance Criteria

1. WHEN a profile retrieval request is received from an authenticated User, THE Profile_Service SHALL return the User's CNI, nom, email, role, and date_inscription.
2. WHEN a profile update request is received with a new nom or email, THE Profile_Service SHALL validate the provided values, update the corresponding fields for the authenticated User, and return HTTP 200 with the updated profile fields.
3. IF a profile update request provides an email that does not conform to the standard email format (local-part@domain.tld), THEN THE Profile_Service SHALL reject the update with HTTP 422 and return a validation error specifying the email field.
4. IF a profile update request provides a nom exceeding 100 characters, THEN THE Profile_Service SHALL reject the update with HTTP 422 and return a validation error specifying the maximum name length.
5. IF a profile update request provides an email already associated with a different User, THEN THE Profile_Service SHALL reject the update with HTTP 409 and return a uniqueness error specifying the email field.
6. IF a profile update request includes a `cni` or `date_inscription` field, THEN THE Profile_Service SHALL return HTTP 422 and reject the update, indicating these fields are immutable.
7. IF a non-Admin User's profile update request includes a `role` field, THEN THE Profile_Service SHALL return HTTP 403 and reject the update, indicating role changes require Admin privileges.
8. IF a profile update request body is empty or contains no recognised updatable fields, THEN THE Profile_Service SHALL return HTTP 422 and indicate that at least one updatable field (nom or email) must be provided.

---

### Requirement 7: Profile Picture Upload and History

**User Story:** As an authenticated user, I want to upload a profile picture, so that my account displays my current photo and a history of past profile pictures is retained.

#### Acceptance Criteria

1. WHEN a profile picture upload request is received with a valid image file (JPEG, PNG, or WebP), THE Profile_Service SHALL store the image in Supabase_Storage and create a new PhotoProfil record linked to the User's CNI, returning HTTP 201 with the new PhotoProfil's id_photo, url_photo, and date_upload.
2. WHEN a PhotoProfil record is created, THE Profile_Service SHALL set date_upload to the current UTC timestamp.
3. WHEN a profile picture is stored in Supabase_Storage, THE Profile_Service SHALL persist the returned Supabase_Storage URL in the PhotoProfil record's url_photo field.
4. THE Profile_Service SHALL retain all past PhotoProfil records for a User and SHALL NOT delete or overwrite previous PhotoProfil entries when a new profile picture is uploaded.
5. IF an uploaded file's MIME type is not `image/jpeg`, `image/png`, or `image/webp`, THEN THE Profile_Service SHALL reject the upload with HTTP 422 and return an error naming the invalid format and listing the accepted formats (JPEG, PNG, WebP).
6. IF an uploaded image file has zero bytes, THEN THE Profile_Service SHALL reject the upload with HTTP 422 and return an error indicating the file is empty, regardless of any format headers present.
7. IF an uploaded image exceeds 5 MB in size, THEN THE Profile_Service SHALL reject the upload with HTTP 413 and return an error stating the 5 MB size limit.
8. IF Supabase_Storage is unavailable during an upload attempt, THEN THE Profile_Service SHALL return HTTP 503 and a service-unavailability error without creating a PhotoProfil record.
9. WHEN a photo history retrieval request is received, THE Profile_Service SHALL return all PhotoProfil records for the authenticated User ordered by date_upload descending; if the User has no PhotoProfil records, the response SHALL be HTTP 200 with an empty list.

---

### Requirement 8: Manual Mensuration Entry Creation

**User Story:** As an authenticated Client, I want to manually record a set of body measurements, so that my measurement history is kept up to date even without using the camera feature.

#### Acceptance Criteria

1. WHEN a manual measurement creation request is received with positive numeric values (in centimetres) for tour_poitrine, tour_taille, tour_hanches, longueur_bras, and hauteur, THE Measurement_Service SHALL create a new Mensuration record linked to the authenticated User's CNI.
2. WHEN a Mensuration record is created, THE Measurement_Service SHALL set date_mensuration to the current UTC timestamp.
3. IF any submitted measurement value is less than or equal to zero, THEN THE Measurement_Service SHALL reject the entire request with HTTP 422 and return a validation error body listing every invalid field, as zero and negative values are not physically valid body measurements.
4. IF any submitted measurement value is non-numeric or exceeds 300 cm, THEN THE Measurement_Service SHALL reject the request with HTTP 422 and return a validation error identifying each offending field and stating the accepted range (greater than 0, at most 300 cm).
5. IF the Measurement_Service rejects a request due to invalid values and fails to return a validation error response, THEN THE Measurement_Service SHALL treat the failure to return an error response as a system failure, log a critical error, and ensure no partial Mensuration record is persisted.
6. WHEN a Mensuration record is successfully created, THE Measurement_Service SHALL return HTTP 201 with the generated id_mesure, tour_poitrine, tour_taille, tour_hanches, longueur_bras, hauteur, and date_mensuration.

---

### Requirement 9: Automated Mensuration Entry from Module 2

**User Story:** As the system, I want to automatically create a Mensuration entry when Module 2 emits a `measurements.estimated` event, so that camera-derived measurements are transparently stored in the authenticated user's history.

#### Acceptance Criteria

1. WHEN the Event_Bus delivers a `measurements.estimated` event containing a valid CNI and positive numeric measurement values, THE Measurement_Service SHALL create a new Mensuration record linked to that CNI.
2. WHEN processing a `measurements.estimated` event, THE Measurement_Service SHALL apply the same validation rules as manual entry (Requirement 8 criteria 3–4) — rejecting non-positive, non-numeric, or out-of-range values.
3. IF the CNI contained in the `measurements.estimated` event does not correspond to an existing User, THEN THE Measurement_Service SHALL reject the event, log a descriptive error entry containing the unknown CNI, and proceed with logging even if the logging subsystem is temporarily unavailable, prioritising rejection over log confirmation.
4. IF the `measurements.estimated` event payload is missing any required measurement field (tour_poitrine, tour_taille, tour_hanches, longueur_bras, or hauteur), THEN THE Measurement_Service SHALL reject the event and log a descriptive error identifying each missing field, without creating a partial Mensuration record.
5. IF a `measurements.estimated` event payload is identical to a previously processed event (same CNI, same measurement values, same source timestamp), THEN THE Measurement_Service SHALL discard the duplicate event without creating a new Mensuration record, ensuring idempotent processing.

---

### Requirement 10: Mensuration History Retrieval

**User Story:** As an authenticated user (Client or Tailor), I want to retrieve all past body measurement entries, so that I can track changes in measurements over time.

#### Acceptance Criteria

1. WHEN a measurement history request is received from an authenticated Client, THE Measurement_Service SHALL return HTTP 200 with all Mensuration records linked to that Client's CNI, ordered by date_mensuration descending.
2. WHEN a measurement history request is received from an authenticated Tailor for an assigned Client, THE Measurement_Service SHALL return HTTP 200 with all Mensuration records for that Client, ordered by date_mensuration descending.
3. IF a Tailor requests measurement history for a Client not assigned to them, THEN THE Measurement_Service SHALL return HTTP 403.
4. THE Measurement_Service SHALL always include id_mesure, tour_poitrine, tour_taille, tour_hanches, longueur_bras, hauteur, and date_mensuration in every Mensuration record returned by the history endpoint.
5. IF a Client has no Mensuration records, THEN THE Measurement_Service SHALL return HTTP 200 with an empty list.

---

### Requirement 11: Send User Profile Data to Module 5

**User Story:** As the system, I want to publish the selected measurement history to Module 5's Ease Margin Engine, so that ease calculations are based on accurate and current body data.

#### Acceptance Criteria

1. WHEN the Ease Margin Engine requests body data for a User, THE Profile_Service SHALL publish a `user.profile_data` event to the Event_Bus containing the User's CNI and their Mensuration entries selected for the current styling session.
2. WHEN no explicit selection exists for the current session, THE Profile_Service SHALL include the single most-recently-dated Mensuration record for the User in the `user.profile_data` event payload.
3. IF the requested User has no Mensuration records, THEN THE Profile_Service SHALL publish a `user.profile_data.error` event to the Event_Bus with a payload indicating insufficient measurement data, and SHALL NOT publish a `user.profile_data` event.
4. IF the requested User's CNI does not correspond to an existing User, THEN THE Profile_Service SHALL publish a `user.profile_data.error` event to the Event_Bus with a payload indicating the User was not found, and SHALL NOT publish a `user.profile_data` event.

---

### Requirement 12: Archive Report from Module 7

**User Story:** As an authenticated Client, I want generated reports from Module 7 to be automatically archived in my account history, so that I can consult past results at any time.

#### Acceptance Criteria

1. WHEN the Event_Bus delivers a `report.saved` event from Module 7, THE Profile_Service SHALL associate the report reference with the Client identified by the CNI in the event payload.
2. WHEN a `report.saved` event is processed, THE Profile_Service SHALL set the archive timestamp to the current UTC time at the moment the Profile_Service processes the event.
3. IF the CNI in the `report.saved` event does not correspond to an existing User, THEN THE Profile_Service SHALL discard the event without persisting any record and log an error entry identifying the unknown CNI.
4. IF a `report.saved` event is delivered with a report ID that is already archived for the given CNI, THEN THE Profile_Service SHALL silently discard the duplicate event without creating a second archive record.
5. WHEN an authenticated Client requests their report history, THE Profile_Service SHALL return HTTP 200 with all archived report references for that Client ordered by archive timestamp descending, each entry containing at minimum the report ID and its date_generation; if the Client has no archived reports, the response SHALL be an empty list.

---

### Requirement 13: Admin User Management

**User Story:** As an Admin, I want to list, view, and deactivate user accounts, so that I can maintain the integrity and security of the platform.

#### Acceptance Criteria

1. WHILE a User is authenticated with the `Admin` role, THE Profile_Service SHALL provide an endpoint to list all registered Users returning each User's CNI, nom, email, role, is_active status, and date_inscription.
2. WHEN an Admin submits a role change request for a non-Admin User, THE Profile_Service SHALL update that User's role to the submitted valid value and return HTTP 200 with the updated User record.
3. IF an Admin submits a role change request with an invalid role value (not one of `Client`, `Tailor`, `Admin`), THEN THE Profile_Service SHALL reject the request with HTTP 422 and return a validation error listing the three accepted values.
4. IF an Admin attempts to change the role of another Admin User, THEN THE Profile_Service SHALL reject the request with HTTP 403 indicating that Admin role assignments are not permitted through this endpoint.
5. WHILE a User is authenticated with the `Admin` role, THE Profile_Service SHALL provide an endpoint to deactivate a User account by setting the target User's `is_active` flag to `false`, returning HTTP 200 confirming deactivation.
6. IF a deactivated User attempts to authenticate, THEN THE Auth_Service SHALL return HTTP 401 with an error message indicating the account has been deactivated.
7. IF an Admin attempts to deactivate an account that is already inactive, THEN THE Profile_Service SHALL return HTTP 200 (idempotent) without modifying the record.

---

## Correctness Properties (Property-Based Testing)

The following properties must hold for all valid inputs and are designed to be verified using property-based testing (e.g., Hypothesis for Python).

### Property 1: Password Hashing — Irreversibility

For all plaintext passwords `p` of length ≥ 8 characters, the Auth_Service's hashing function `h` satisfies:
- `h(p) ≠ p` — the hash is never identical to the plaintext.
- `verify(p, h(p)) == True` — the original password always verifies against its own hash.
- `p1 ≠ p2 ⟹ verify(p1, h(p2)) == False` — a different password never verifies against another's hash.

**Pattern:** Round-Trip (verify is the non-strict inverse of hash)

---

### Property 2: CNI and Email Uniqueness — Idempotence of Rejection

For any set of registration requests containing duplicate CNI or email values, repeated registration attempts with the same CNI or email SHALL always be rejected. The total number of User records with a given CNI or email value shall always equal exactly 1 after any number of registration attempts.

**Pattern:** Invariant — cardinality of users per CNI = 1, cardinality of users per email = 1

---

### Property 3: JWT Round-Trip — Encode/Decode Consistency

For all valid User records `u` (any CNI, role, valid expiry), the JWT produced by `issue(u)` shall decode back to the same CNI and role:
- `decode(issue(u)).cni == u.cni`
- `decode(issue(u)).role == u.role`

**Pattern:** Round-Trip (decode is the inverse of issue)

---

### Property 4: Measurement Validation — Rejection of Non-Positive Values

For any Mensuration creation request where at least one of `tour_poitrine`, `tour_taille`, `tour_hanches`, `longueur_bras`, or `hauteur` is ≤ 0, the Measurement_Service SHALL always reject the request. No Mensuration record shall be created.

**Pattern:** Error Conditions — exhaustive bad-input rejection

---

### Property 5: Mensuration History Ordering Invariant

For any User with n ≥ 2 Mensuration entries, the list returned by the measurement history endpoint SHALL satisfy:
- `entries[i].date_mensuration >= entries[i+1].date_mensuration` for all i in 0..n-2 (descending order).
- `len(returned_entries) == n` — no entries are omitted or duplicated.

**Pattern:** Invariant — sort order and completeness preserved across arbitrary insertions

---

### Property 6: Profile Photo History — Append-Only Invariant

For any User who has uploaded k profile pictures, uploading a new picture shall result in exactly k+1 PhotoProfil records for that User. Past records shall be unmodified (url_photo and date_upload unchanged).

**Pattern:** Invariant — append-only collection, no destructive updates to prior entries

---

### Property 7: Role-Based Access — Authorisation Consistency

For all pairs (User u, endpoint e) where u.role ∉ authorised_roles(e), every request from u to e shall be rejected with 403. This property must hold for arbitrarily generated (user, role, endpoint) combinations.

**Pattern:** Metamorphic — permission verdict is purely a function of role membership, independent of other user attributes (CNI, name, measurement count)

---

### Property 8: Measurement Event Idempotence Guard

Processing the same `measurements.estimated` event payload twice (same CNI, same measurement values, same timestamp) shall not create duplicate Mensuration records. The number of Mensuration records for a User shall be equal to the number of distinct valid events processed, not the number of times an event was delivered.

**Pattern:** Idempotence — repeated delivery of the same event produces no additional state change
