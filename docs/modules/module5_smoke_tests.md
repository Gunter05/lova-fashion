# Module 5 — Smoke Test Guide
# Ease Allowance Calculation Engine (Moteur de calcul d'aisance)

## Prerequisites

1. Server running locally:
   ```
   cd backend
   uvicorn main:app --reload --port 8000
   ```
2. Migrations 005 and 006 applied to your Supabase project (in order).
3. Module 2 has at least one completed session (`status = success`) for User A —
   you need its `session_id` as `$SESSION`.
4. Module 3 has at least three fabric records in the database — one per elasticity
   category (`rigid`, `semi-stretch`, `stretch`). Obtain their IDs as:
   - `$FABRIC_RIGID`
   - `$FABRIC_SEMI`
   - `$FABRIC_STRETCH`
5. Valid JWT tokens for two Supabase users:
   - `<TOKEN_A>` — owns `$SESSION`
   - `<TOKEN_B>` — a different user with no sessions

**Base URL:** `http://localhost:8000/api/v1/ease`

---

## T-07.1 — Happy Path: Rigid Fabric (+4 cm)

**Covers:** AC-01.5, AC-02.1

```bash
curl -s -X POST http://localhost:8000/api/v1/ease/adjustments \
  -H "Authorization: Bearer <TOKEN_A>" \
  -H "Content-Type: application/json" \
  -d "{\"session_id\": \"$SESSION\", \"fabric_id\": \"$FABRIC_RIGID\"}"
```

**Expected:** HTTP **201**
```json
{
  "adjustment_id": "<UUID>",
  "session_id": "<SESSION>",
  "fabric_id": "<FABRIC_RIGID>",
  "fabric_name": "Pagne Wax",
  "elasticity_category": "rigid",
  "ease_source": "rule",
  "bust":  { "raw_cm": 87.5, "ease_cm": 4.0, "adjusted_cm": 91.5 },
  "waist": { "raw_cm": 68.0, "ease_cm": 4.0, "adjusted_cm": 72.0 },
  "hips":  { "raw_cm": 93.0, "ease_cm": 4.0, "adjusted_cm": 97.0 },
  "calculated_at": "...",
  "data_integrity_warning": false
}
```

**Verify:**
- [ ] HTTP status is **201** (new record)
- [ ] `adjusted_cm = raw_cm + 4.0` for every zone
- [ ] `ease_source = "rule"`
- [ ] `data_integrity_warning = false`

Save `adjustment_id` as `$ADJ_RIGID`.

---

## T-07.2 — Upsert / Recompute (same session + fabric)

**Covers:** AC-01.6

```bash
curl -s -X POST http://localhost:8000/api/v1/ease/adjustments \
  -H "Authorization: Bearer <TOKEN_A>" \
  -H "Content-Type: application/json" \
  -d "{\"session_id\": \"$SESSION\", \"fabric_id\": \"$FABRIC_RIGID\"}"
```

**Expected:** HTTP **200** (not 201)

**Verify:**
- [ ] HTTP status is **200**
- [ ] `adjustment_id` in response equals `$ADJ_RIGID` (same record, not a new one)
- [ ] `adjusted_cm` values are identical (raw measurements unchanged)
- [ ] Confirm `updated_at` has changed in Supabase Table Editor:
  ```sql
  SELECT id, updated_at FROM measurement_adjustments WHERE id = '<ADJ_RIGID>';
  ```

---

## T-07.3 — All Three Elasticity Categories

**Covers:** AC-02.1, AC-02.2, AC-02.3

### Semi-stretch (+2 cm)

```bash
curl -s -X POST http://localhost:8000/api/v1/ease/adjustments \
  -H "Authorization: Bearer <TOKEN_A>" \
  -H "Content-Type: application/json" \
  -d "{\"session_id\": \"$SESSION\", \"fabric_id\": \"$FABRIC_SEMI\"}"
```

**Expected:** HTTP 201, `ease_cm = 2.0` for all zones, `ease_source = "rule"`.

### Stretch (−2 cm)

```bash
curl -s -X POST http://localhost:8000/api/v1/ease/adjustments \
  -H "Authorization: Bearer <TOKEN_A>" \
  -H "Content-Type: application/json" \
  -d "{\"session_id\": \"$SESSION\", \"fabric_id\": \"$FABRIC_STRETCH\"}"
```

**Expected:** HTTP 201, `ease_cm = -2.0` for all zones, `ease_source = "rule"`.

**Verify for stretch:**
- [ ] `adjusted_cm = raw_cm - 2.0` for every zone
- [ ] No adjusted value is negative (floor clamp active if raw < 2.0 cm — unlikely for body measurements)

---

## T-07.4 — Default Fallback (unknown elasticity)

**Covers:** AC-02.4

Temporarily set a fabric's category to an unknown value directly in Supabase:
```sql
UPDATE fabric_categories SET reference_rigidity_level = 'unknown_type'
WHERE id = (SELECT category_id FROM fabrics WHERE id = '<FABRIC_RIGID>');
```

Then call:
```bash
curl -s -X POST http://localhost:8000/api/v1/ease/adjustments \
  -H "Authorization: Bearer <TOKEN_A>" \
  -H "Content-Type: application/json" \
  -d "{\"session_id\": \"$SESSION\", \"fabric_id\": \"$FABRIC_RIGID\"}"
```

**Expected:** HTTP 200 (upsert), response is **not** a 4xx error.
```json
{
  "ease_source": "default_fallback",
  "bust":  { "ease_cm": 3.0, "adjusted_cm": "<raw + 3.0>" },
  ...
}
```

**Verify:**
- [ ] `ease_source = "default_fallback"`
- [ ] `ease_cm = 3.0` for all zones
- [ ] Server logs contain a `WARNING` line like:
  `EaseEngine [session=... fabric=...]: Catégorie d'élasticité inconnue ('unknown_type') — aisance par défaut +3 cm appliquée.`

Restore the original value after the test:
```sql
UPDATE fabric_categories SET reference_rigidity_level = 'rigid'
WHERE id = (SELECT category_id FROM fabrics WHERE id = '<FABRIC_RIGID>');
```

---

## T-07.5 — 424 Guard (no completed measurement)

**Covers:** AC-01.3

Use a Module 2 session that is still in `processing` or `empty` status:
```bash
curl -s -X POST http://localhost:8000/api/v1/ease/adjustments \
  -H "Authorization: Bearer <TOKEN_A>" \
  -H "Content-Type: application/json" \
  -d "{\"session_id\": \"<INCOMPLETE_SESSION_ID>\", \"fabric_id\": \"$FABRIC_RIGID\"}"
```

**Expected:** HTTP **424**
```json
{
  "detail": "Aucune mensuration validée pour cette session. Complétez d'abord la prise de mesure."
}
```

---

## T-07.6 — Multi-Fabric Comparison List

**Covers:** AC-06.1, US-06

After completing T-07.1 and T-07.3, list all adjustments for the session:
```bash
curl -s \
  "http://localhost:8000/api/v1/ease/sessions/$SESSION/adjustments" \
  -H "Authorization: Bearer <TOKEN_A>"
```

**Expected:** HTTP 200
```json
{
  "adjustments": [
    {
      "adjustment_id": "<UUID>",
      "fabric_name": "Jersey",
      "elasticity_category": "stretch",
      "ease_source": "rule",
      "adjusted_bust_cm": 85.5,
      ...
    },
    {
      "adjustment_id": "<UUID>",
      "fabric_name": "Tissu semi-stretch",
      "elasticity_category": "semi-stretch",
      ...
    },
    {
      "adjustment_id": "<ADJ_RIGID>",
      "fabric_name": "Pagne Wax",
      "elasticity_category": "rigid",
      ...
    }
  ],
  "total": 3
}
```

**Verify:**
- [ ] All three adjustments present, ordered newest first
- [ ] `total` equals the number of items in the array
- [ ] Each has distinct `adjusted_bust_cm` values reflecting different ease deltas

### Empty list (no adjustments yet)

```bash
curl -s \
  "http://localhost:8000/api/v1/ease/sessions/<NEW_SESSION_ID>/adjustments" \
  -H "Authorization: Bearer <TOKEN_A>"
```

**Expected:** HTTP 200, `{"adjustments": [], "total": 0}` (AC-06.2)

---

## T-07.7 — Cross-User Isolation

**Covers:** AC-05.2, NFR-03

### GET adjustment with wrong user

```bash
curl -s \
  "http://localhost:8000/api/v1/ease/adjustments/$ADJ_RIGID" \
  -H "Authorization: Bearer <TOKEN_B>"
```

**Expected:** HTTP **403**
```json
{ "detail": "Vous n'êtes pas autorisé à accéder à cet ajustement." }
```

### POST adjustment on another user's session

```bash
curl -s -X POST http://localhost:8000/api/v1/ease/adjustments \
  -H "Authorization: Bearer <TOKEN_B>" \
  -H "Content-Type: application/json" \
  -d "{\"session_id\": \"$SESSION\", \"fabric_id\": \"$FABRIC_RIGID\"}"
```

**Expected:** HTTP **403**

### No token

```bash
curl -s -X POST http://localhost:8000/api/v1/ease/adjustments \
  -H "Content-Type: application/json" \
  -d "{\"session_id\": \"$SESSION\", \"fabric_id\": \"$FABRIC_RIGID\"}"
```

**Expected:** HTTP **401** (AC-01.1)

### GET adjustment by ID — happy path

```bash
curl -s \
  "http://localhost:8000/api/v1/ease/adjustments/$ADJ_RIGID" \
  -H "Authorization: Bearer <TOKEN_A>"
```

**Expected:** HTTP 200, full `AdjustmentResponse` with `bust`, `waist`, `hips` zone details.

---

## FastAPI Interactive Docs

All endpoints are also explorable at:
```
http://localhost:8000/docs
```
Use the **Authorize** button and enter `Bearer <TOKEN_A>` to authenticate in Swagger UI.
