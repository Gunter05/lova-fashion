# Requirements — Module 2: Photo Capture & Measurement Estimation
# (Prise de mesure — Estimation de mensuration par photo)

## Overview

This module lets an authenticated user submit two photos (front-view and profile-view) plus
their stature (height in centimetres) and receive, without a physical tape measure, their
estimated raw anatomical measurements (bust, waist, hips) together with their body-shape
classification. The output is persisted and consumed by Module 5 (Ease Allowance Engine)
and Module 6 (Compatibility Engine).

---

## Actors

| Actor | Description |
|---|---|
| **Authenticated User** | End client who submits photos and height to get measurements |
| **System (CV Pipeline)** | MediaPipe + ellipse geometry service that analyses photos |
| **Module 1 — Auth** | Provides the authenticated user identity (JWT token) |
| **Module 5 — Ease Engine** | Consumes the raw measurement profile produced by this module |
| **Module 6 — Compatibility Engine** | Consumes the body-shape classification produced by this module |

---

## User Stories & Acceptance Criteria (EARS Format)

---

### US-01 — Create a Capture Session

**As an** authenticated user,  
**I want to** initiate a new capture session,  
**so that** I can submit my photos and height and receive my estimated measurements.

#### AC-01.1 — Session creation requires authentication
> **When** a request to create a capture session is received without a valid JWT,  
> **the system shall** return HTTP 401 Unauthorized.

#### AC-01.2 — Session is created with status `empty`
> **When** an authenticated user sends a valid POST `/sessions` request (no payload required beyond auth),  
> **the system shall** create a new capture session with status `empty`, record the `user_id` and `created_at` timestamp, and return HTTP 201 with the new `session_id`.

#### AC-01.3 — Only one session is marked active per user
> **When** a new session transitions to status `success`,  
> **the system shall** automatically set `is_active = false` on all previous sessions belonging to the same user, so that only the newest successful session carries `is_active = true`.

---

### US-02 — Upload Front and Profile Photos

**As an** authenticated user,  
**I want to** upload my front-view and profile-view photos to an existing session,  
**so that** the system can analyse them to estimate my measurements.

#### AC-02.1 — Both photos must be present
> **When** a photo upload request is received for a session that already has one photo but is missing the other,  
> **the system shall** accept each photo individually and only mark the session ready for processing once both photos are present.

#### AC-02.2 — MIME-type validation
> **When** an uploaded file has a MIME type other than `image/jpeg` or `image/png`,  
> **the system shall** reject it with HTTP 422 Unprocessable Entity and the message `"Format non supporté. Utilisez JPEG ou PNG."`.

#### AC-02.3 — File-size validation
> **When** an uploaded file exceeds 10 MB,  
> **the system shall** reject it with HTTP 422 and the message `"Fichier trop volumineux. Limite : 10 Mo."`.

#### AC-02.4 — Body-presence validation (AI gate)
> **When** basic file validation passes but MediaPipe Pose cannot detect a full human body in the photo,  
> **the system shall** reject the upload with HTTP 422 and the message `"Aucun corps humain détecté. Reprenez la photo dans un endroit bien éclairé avec des vêtements ajustés."`.

#### AC-02.5 — Photo stored in Supabase Storage
> **When** a photo passes all validation steps,  
> **the system shall** store it at path `captures/{user_id}/{session_id}/front.jpg` or `captures/{user_id}/{session_id}/profile.jpg` and persist the public URL in the session record.

#### AC-02.6 — Cannot upload to a completed or non-existent session
> **When** a photo upload targets a session with status `success`, or a session that does not belong to the authenticated user, or a session that does not exist,  
> **the system shall** return HTTP 403 Forbidden or HTTP 404 Not Found respectively.

---

### US-03 — Submit Stature

**As an** authenticated user,  
**I want to** provide my height in centimetres as part of the session,  
**so that** the system can convert pixel dimensions into real-world measurements.

#### AC-03.1 — Stature range validation
> **When** the submitted stature is not a numeric value strictly between 100 cm and 250 cm (inclusive),  
> **the system shall** return HTTP 422 with the message `"La stature doit être comprise entre 100 cm et 250 cm."`.

#### AC-03.2 — Stature persisted on session
> **When** a valid stature is submitted,  
> **the system shall** persist it (as `DECIMAL(5,1)`) on the corresponding capture session and return HTTP 200 with the updated session object.

---

### US-04 — Trigger Measurement Estimation

**As an** authenticated user,  
**I want to** start the measurement estimation process once both photos and my stature are ready,  
**so that** the system can compute my raw measurements without me waiting for a synchronous response.

#### AC-04.1 — Processing requires all three inputs
> **When** a process request is received but the session is missing either photo or a valid stature,  
> **the system shall** return HTTP 422 with a clear field-level error list.

#### AC-04.2 — Session transitions to `processing` immediately
> **When** a valid process request is accepted,  
> **the system shall** set session status to `processing`, return HTTP 202 Accepted with the `session_id` and a polling URL (`/sessions/{session_id}/status`), and enqueue the estimation job asynchronously (background task).

#### AC-04.3 — Cannot re-trigger a session already `processing` or `success`
> **When** a process request targets a session that is already `processing` or `success`,  
> **the system shall** return HTTP 409 Conflict with the message `"Cette session est déjà en cours de traitement ou terminée."`.

---

### US-05 — Poll Session Status

**As an** authenticated user,  
**I want to** poll the status of my capture session,  
**so that** I know when the estimation is complete or has failed.

#### AC-05.1 — Returns current status and timestamps
> **When** an authenticated user calls GET `/sessions/{session_id}/status`,  
> **the system shall** return HTTP 200 with the fields: `session_id`, `status` (`empty` | `processing` | `success` | `failed`), `created_at`, `updated_at`.

#### AC-05.2 — Returns results when status is `success`
> **When** the session status is `success`,  
> **the system shall** include in the status response: `bust_cm`, `waist_cm`, `hips_cm` (each `DECIMAL(5,1)`), and `silhouette_code` (one of `HOURGLASS`, `RECTANGLE`, `PEAR`, `INVERTED_TRIANGLE`, `APPLE`).

#### AC-05.3 — Returns error detail when status is `failed`
> **When** the session status is `failed`,  
> **the system shall** include in the status response a `failure_reason` string and a `retry_allowed: true` flag.

---

### US-06 — Retry After Failure

**As an** authenticated user,  
**I want to** re-upload photos to a failed session without creating a new one,  
**so that** I can correct the issue (lighting, clothing) without cluttering my measurement history.

#### AC-06.1 — Failed session accepts new photos
> **When** a session is in `failed` status,  
> **the system shall** allow the user to upload new front and/or profile photos to that same session (overwriting the stored URLs) and reset the session status to `empty`.

#### AC-06.2 — Retry count tracked
> **When** a retry upload is accepted on a failed session,  
> **the system shall** increment a `retry_count` field on the session record (no maximum enforced, for audit purposes).

---

### US-07 — View Measurement History

**As an** authenticated user,  
**I want to** list all my past successful capture sessions,  
**so that** I can track how my measurements have changed over time.

#### AC-07.1 — Returns only the caller's sessions
> **When** an authenticated user calls GET `/sessions`,  
> **the system shall** return only sessions belonging to that user, ordered by `created_at` descending, with HTTP 200.

#### AC-07.2 — Active session flagged
> **When** listing sessions,  
> **the system shall** include an `is_active` boolean field on each session item so the client can identify the current active measurement profile.

---

### US-08 — Body Shape Classification

**As a** system process (running after successful landmark detection),  
**I want to** classify the user's body shape from computed bust/waist/hip ratios,  
**so that** downstream modules (5 and 6) receive a standardised silhouette code.

#### AC-08.1 — Classification uses the agreed ratio ruleset
> **When** raw measurements are computed, the system shall apply the following rules in priority order:

| Priority | Silhouette | Condition |
|---|---|---|
| 1 | `HOURGLASS` | `waist/bust ≤ 0.75` AND `waist/hips ≤ 0.75` AND `|bust − hips| ≤ 5 cm` |
| 2 | `PEAR` | `hips > bust + 5 cm` AND `waist < hips` |
| 3 | `INVERTED_TRIANGLE` | `bust > hips + 5 cm` |
| 4 | `APPLE` | `waist ≥ bust` OR `waist ≥ hips` |
| 5 | `RECTANGLE` | none of the above |

#### AC-08.2 — Exactly one silhouette code stored
> **When** classification is complete,  
> **the system shall** persist exactly one `silhouette_code` value linked to the raw measurement record.

---

## Non-Functional Requirements

| ID | Requirement |
|---|---|
| NFR-01 | The estimation background task must complete within **30 seconds** under normal load. |
| NFR-02 | Photo uploads must complete within **5 seconds** per file on a standard connection. |
| NFR-03 | All endpoints are accessible only to authenticated users (Bearer JWT). |
| NFR-04 | Supabase Storage RLS policies must be scoped to `captures/{user_id}/` to prevent cross-user access. |
| NFR-05 | Stored measurements use `DECIMAL(5,1)` precision (one decimal place). |
| NFR-06 | All error responses follow the unified `{"detail": "<message>"}` JSON envelope. |
