# Tech Stack

## Backend
- Python, FastAPI (`main.py` as entry point)
- Database: PostgreSQL managed via **Supabase**
- Photo storage (measurements, fabrics): **Supabase Storage**
- Hosting: **Render.com** — connected to the GitHub repo, auto-redeploys on every push to
  `main`
- One subfolder per module group in `backend/app/modules/`:
  - `auth_catalogues/` → modules 1, 3, 4
  - `measurements/` → module 2
  - `business_rules/` → modules 5, 6, 7

## Frontend
- **Decision pending**: React or Flutter (see `frontend/README.md` for the decision criteria).
- Hosting: **Vercel** — connected to the GitHub repo (root directory: `frontend/`),
  auto-deploy on every push, free HTTPS URL.
- Once the framework is chosen, update this section and scaffold the project.

## Deployment notes (mono-repo)
- On Render: create a service pointing at the `backend/` subfolder.
- On Vercel: create a project pointing at the `frontend/` subfolder.
- Both platforms natively support mono-repos via this root-directory setting — no need to
  split into two separate repos.
