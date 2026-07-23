# Module 2 — Smoke Test Guide
# Photo Capture & Measurement Estimation (Prise de mesure)

## Prerequisites

Before running any test:

1. Server is running locally:
   ```
   cd backend
   uvicorn main:app --reload --port 8000
   ```
2. All four SQL migrations (001–004) have been applied to your Supabase project.
3. The `captures` bucket exists in Supabase Storage (private, RLS active).
4. `.env` contains all required variables:
   - `DATABASE_URL`
   - `SUPABASE_URL`
   - `SUPABASE_KEY`
   - `SUPABASE_JWT_SECRET`
   - `SUPABASE_STORAGE_BUCKET=captures`

5. You have at least **two valid Supabase user accounts** (User A and User B) and their
   respective JWT access tokens. Obtain a token by calling the Supabase Auth REST API:
   ```
   POST https://<project>.supabase.co/auth/v1/token?grant_type=password
   Content-Type: application/json

   { "email": "user@example.com", "password": "yourpassword" }
   ```
   Copy `access_token` from the response — use this as `<TOKEN_A>` / `<TOKEN_B>` below.

6. You have two test images ready:
   - `front_valid.jpg`   — full-body JPEG, person standing facing forward, good lighting
   - `profile_valid.jpg` — full-body JPEG, person standing side-on, good lighting
   - `no_body.jpg`       — any image with no human body (e.g. a landscape photo)

**Base URL:** `http://localhost:8000/api/v1/measurements`

---

## T-09.1 — Happy Path: Full Estimation Flow

**Covers:** AC-01.2, AC-02.5, AC-03.2, AC-04.2, AC-05.1, AC-05.2

### Step 1 — Create a session

```bash
curl -s -X POST http://localhost:8000/api/v1/measurements/sessions \
  -H "Authorization: Bearer <TOKEN_A>"
```

**Expected:** HTTP 201
```json
{
  "session_id": "<UUID>",
  "status": "empty",
  "created_at": "2026-07-22T..."
}
```
Save `session_id` as `$SESSION`.

---

### Step 2 — Upload front photo

```bash
curl -s -X PUT \
  "http://localhost:8000/api/v1/measurements/sessions/$SESSION/photos/front" \
  -H "Authorization: Bearer <TOKEN_A>" \
  -F "file=@front_valid.jpg;type=image/jpeg"
```

**Expected:** HTTP 200
```json
{
  "session_id": "<UUID>",
  "view": "front",
  "photo_url": "https://<project>.supabase.co/storage/v1/object/public/captures/...",
  "status": "empty"
}
```

---

### Step 3 — Upload profile photo

```bash
curl -s -X PUT \
  "http://localhost:8000/api/v1/measurements/sessions/$SESSION/photos/profile" \
  -H "Authorization: Bearer <TOKEN_A>" \
  -F "file=@profile_valid.jpg;type=image/jpeg"
```

**Expected:** HTTP 200, `"status": "empty"`

---

### Step 4 — Set stature

```bash
curl -s -X PATCH \
  "http://localhost:8000/api/v1/measurements/sessions/$SESSION/stature" \
  -H "Authorization: Bearer <TOKEN_A>" \
  -H "Content-Type: application/json" \
  -d '{"stature_cm": 172.0}'
```

**Expected:** HTTP 200
```json
{
  "session_id": "<UUID>",
  "entered_stature": "172.0",
  "status": "empty"
}
```

---

### Step 5 — Trigger estimation

```bash
curl -s -X POST \
  "http://localhost:8000/api/v1/measurements/sessions/$SESSION/process" \
  -H "Authorization: Bearer <TOKEN_A>"
```

**Expected:** HTTP 202
```json
{
  "session_id": "<UUID>",
  "status": "processing",
  "polling_url": "http://localhost:8000/api/v1/measurements/sessions/<UUID>/status"
}
```

---

### Step 6 — Poll until success

Repeat every 3 seconds until `status` is no longer `"processing"`:

```bash
curl -s \
  "http://localhost:8000/api/v1/measurements/sessions/$SESSION/status" \
  -H "Authorization: Bearer <TOKEN_A>"
```

**Expected final state:** HTTP 200, `"status": "success"`
```json
{
  "session_id": "<UUID>",
  "status": "success",
  "created_at": "...",
  "updated_at": "...",
  "retry_allowed": false,
  "failure_reason": null,
  "measurements": {
    "bust_cm": "87.5",
    "waist_cm": "68.0",
    "hips_cm": "93.0",
    "silhouette_code": "HOURGLASS"
  }
}
```

**Verify:**
- [ ] `measurements` is not null
- [ ] `bust_cm`, `waist_cm`, `hips_cm` are non-zero decimals with one decimal place
- [ ] `silhouette_code` is one of: `HOURGLASS`, `PEAR`, `INVERTED_TRIANGLE`, `APPLE`, `RECTANGLE`
- [ ] `retry_allowed` is `false`

---

### Step 7 — Re-trigger guard (AC-04.3)

```bash
curl -s -X POST \
  "http://localhost:8000/api/v1/measurements/sessions/$SESSION/process" \
  -H "Authorization: Bearer <TOKEN_A>"
```

**Expected:** HTTP 409
```json
{ "detail": "Cette session est déjà en cours de traitement ou terminée." }
```

---

## T-09.2 — Failure Path and Retry

**Covers:** AC-02.4, AC-06.1, AC-06.2

### Step 1 — Create a new session

```bash
curl -s -X POST http://localhost:8000/api/v1/measurements/sessions \
  -H "Authorization: Bearer <TOKEN_A>"
```

Save new `session_id` as `$SESSION2`.

---

### Step 2 — Upload a photo with no human body

```bash
curl -s -X PUT \
  "http://localhost:8000/api/v1/measurements/sessions/$SESSION2/photos/front" \
  -H "Authorization: Bearer <TOKEN_A>" \
  -F "file=@no_body.jpg;type=image/jpeg"
```

**Expected:** HTTP 422
```json
{
  "detail": "Aucun corps humain détecté. Reprenez la photo dans un endroit bien éclairé avec des vêtements ajustés."
}
```
Session status remains `"empty"` — no state change on validation failure.

---

### Step 3 — Trigger with only one photo (missing profile)

Upload a valid front photo first:
```bash
curl -s -X PUT \
  "http://localhost:8000/api/v1/measurements/sessions/$SESSION2/photos/front" \
  -H "Authorization: Bearer <TOKEN_A>" \
  -F "file=@front_valid.jpg;type=image/jpeg"
```

Then trigger without stature or profile:
```bash
curl -s -X POST \
  "http://localhost:8000/api/v1/measurements/sessions/$SESSION2/process" \
  -H "Authorization: Bearer <TOKEN_A>"
```

**Expected:** HTTP 422 with field-level errors
```json
{
  "detail": [
    {"field": "profile_photo", "message": "Photo de profil manquante."},
    {"field": "stature_cm",    "message": "La stature n'a pas été renseignée."}
  ]
}
```

---

### Step 4 — Complete upload, trigger, and force a CV failure

Complete the session (valid photos + stature), trigger processing, then poll status.
If the photos cause MediaPipe to fail (e.g. low-quality image):

**Expected poll result:** HTTP 200, `"status": "failed"`
```json
{
  "status": "failed",
  "retry_allowed": true,
  "failure_reason": "Aucun corps humain détecté..."
}
```

---

### Step 5 — Retry: upload new photos to the failed session

```bash
curl -s -X PUT \
  "http://localhost:8000/api/v1/measurements/sessions/$SESSION2/photos/front" \
  -H "Authorization: Bearer <TOKEN_A>" \
  -F "file=@front_valid.jpg;type=image/jpeg"
```

**Expected:** HTTP 200
```json
{
  "session_id": "<UUID>",
  "view": "front",
  "status": "empty"
}
```

**Verify:**
- [ ] `status` has reset to `"empty"` (AC-06.1)
- [ ] `retry_count` has incremented — check in Supabase Table Editor:
  ```sql
  SELECT id, status, retry_count FROM capture_sessions WHERE id = '<SESSION2>';
  ```
  Expected: `retry_count = 1` (AC-06.2)

Repeat Steps 3–5 of T-09.1 to complete the retry flow to `success`.

---

### Additional validation errors

**MIME type rejection** (AC-02.2):
```bash
curl -s -X PUT \
  "http://localhost:8000/api/v1/measurements/sessions/$SESSION2/photos/front" \
  -H "Authorization: Bearer <TOKEN_A>" \
  -F "file=@document.pdf;type=application/pdf"
```
**Expected:** HTTP 422 `"Format non supporté. Utilisez JPEG ou PNG."`

**Stature out of range** (AC-03.1):
```bash
curl -s -X PATCH \
  "http://localhost:8000/api/v1/measurements/sessions/$SESSION2/stature" \
  -H "Authorization: Bearer <TOKEN_A>" \
  -H "Content-Type: application/json" \
  -d '{"stature_cm": 50}'
```
**Expected:** HTTP 422 (Pydantic validation error, `ge=100` constraint)

---

## T-09.3 — Cross-User Isolation

**Covers:** NFR-04

Using `$SESSION` (created by User A), attempt access with User B's token:

### GET status — should be 403
```bash
curl -s \
  "http://localhost:8000/api/v1/measurements/sessions/$SESSION/status" \
  -H "Authorization: Bearer <TOKEN_B>"
```
**Expected:** HTTP 403
```json
{ "detail": "Vous n'êtes pas autorisé à accéder à cette session." }
```

### PUT photo — should be 403
```bash
curl -s -X PUT \
  "http://localhost:8000/api/v1/measurements/sessions/$SESSION/photos/front" \
  -H "Authorization: Bearer <TOKEN_B>" \
  -F "file=@front_valid.jpg;type=image/jpeg"
```
**Expected:** HTTP 403

### GET sessions — User B sees only their own
```bash
curl -s \
  "http://localhost:8000/api/v1/measurements/sessions" \
  -H "Authorization: Bearer <TOKEN_B>"
```
**Expected:** HTTP 200, `sessions` list does **not** contain `$SESSION` (User A's session).

### No token — should be 401
```bash
curl -s \
  "http://localhost:8000/api/v1/measurements/sessions/$SESSION/status"
```
**Expected:** HTTP 401 (no `Authorization` header)

---

## T-09.4 — `is_active` Flag Behaviour

**Covers:** AC-01.3, AC-07.2

Run the full happy path (T-09.1) once more for User A to complete a second session.
Both sessions should now appear in the sessions list.

### List all sessions
```bash
curl -s \
  "http://localhost:8000/api/v1/measurements/sessions" \
  -H "Authorization: Bearer <TOKEN_A>"
```

**Expected:** HTTP 200
```json
{
  "sessions": [
    { "session_id": "<SESSION_NEW>", "status": "success", "is_active": true,  "created_at": "..." },
    { "session_id": "<SESSION_OLD>", "status": "success", "is_active": false, "created_at": "..." }
  ],
  "total": 2
}
```

**Verify:**
- [ ] Exactly one session has `is_active: true` — the most recent successful one (AC-01.3)
- [ ] All prior successful sessions have `is_active: false`
- [ ] Sessions are ordered newest-first (AC-07.1)
- [ ] Confirm in Supabase Table Editor:
  ```sql
  SELECT id, status, is_active, created_at
  FROM capture_sessions
  WHERE user_id = '<USER_A_UUID>'
  ORDER BY created_at DESC;
  ```

---

## FastAPI Interactive Docs

All endpoints are also explorable at:
```
http://localhost:8000/docs
```
Use the "Authorize" button (top right) and enter `Bearer <TOKEN_A>` to authenticate
directly in the Swagger UI.
