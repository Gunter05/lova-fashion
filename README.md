# lova-fashion — Remote Custom-Fit Styling & Pattern-Making

AWS re:Deploy 2026 — Month 1 (July 2026) — Theme: **Fashion**

## Problem & Solution

**The problem.** Custom tailoring in Cameroon depends on an in-person fitting: a client has to
physically visit a tailor to get their measurements taken before a garment can be made. This
is a real barrier for people who can't easily travel to a tailor, or who simply want to explore
a fitted garment remotely before committing.

**Our solution.** A web application that estimates sewing measurements (chest/bust, waist,
hips) remotely, from just two photos (front + side) and the user's height. From there:
- An AI layer validates the detected body shape.
- The system automatically applies the right ease margins based on the rigidity of the
  selected fabric (e.g. a rigid Wax print vs. a stretchy Jersey).
- It checks whether the chosen garment pattern is technically compatible with the fabric and
  body shape.

The result: a garment that fits properly, without an in-person fitting.

## Team

| Name | Role |
|---|---|
| Ousmane | Backend |
| Verdiane | Backend |
| NYNA Amanda | Backend |
| Belvira | Frontend |

## 🔗 Live Links (Most Important!)

- **App (Frontend):** _TODO — add Vercel URL_
- **API Documentation (Swagger):** _TODO — add Render URL + `/docs`_

## Quick Start Guide

### Run the backend locally
```bash
cd backend
python -m venv venv
source venv/bin/activate      # on Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env          # fill in DATABASE_URL, SUPABASE_URL, SUPABASE_KEY
uvicorn main:app --reload
```
FastAPI automatically generates interactive API docs at `http://localhost:8000/docs` —
this is the same page that will be linked above once deployed on Render.

### Run the frontend locally
*Framework decision pending — see `frontend/README.md`.*
- If React: `cd frontend && npm install && npm run dev`
- If Flutter: `cd frontend && flutter pub get && flutter run`

## Architecture

See `.kiro/steering/tech.md` and `.kiro/steering/structure.md` for details.

```
Frontend (React or Flutter) ── hosted on Vercel
        │
Backend FastAPI ── hosted on Render
        │
  ┌─────┴──────┬───────────────┐
Auth &      Measurements   Business
catalogs    (photo         Rules
            analysis, CV)  (ease margins,
                            compatibility,
                            report)
        │
  Supabase (PostgreSQL + Storage for photos)
```

Mono-repo: Render and Vercel are each configured with a different root directory
(`backend/` and `frontend/`) on the same GitHub repo — no need for two separate repos.

## Using Kiro

Each module is specified in `.kiro/specs/<module>/` (requirements → design → tasks) before
being implemented with Kiro's help. See `.kiro/steering/` for the product and technical
context given to Kiro.

## Documentation

- `docs/data-models/` — conceptual data models (CDM) per module
- `docs/modules/` — functional documentation per module (team standard, 10 sections)

## Deployment

### Backend → Render
1. Create a Supabase project (get `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_KEY`).
2. On Render: New Web Service → connect this repo → root directory `backend/` →
   build command `pip install -r requirements.txt` → start command
   `uvicorn main:app --host 0.0.0.0 --port $PORT`.
3. Add the environment variables from `.env.example` in Render's settings.
4. Deploy today, even with just `/health` — get a public URL immediately instead of
   waiting until the end.

### Frontend → Vercel
1. Once the framework is chosen and scaffolded in `frontend/`.
2. On Vercel: New Project → connect this repo → root directory `frontend/`.
3. Every `git push` on `main` triggers an automatic redeploy.
