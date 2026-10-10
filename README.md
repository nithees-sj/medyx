# HealthThread

> One patient, one record, every hospital — and it catches what no single hospital can see.

HealthThread turns scattered medical documents (PDFs, photos, handwritten prescriptions) from many
hospitals into one FHIR R4 record. It flags cross-hospital safety problems, gives doctors a cited
AI copilot, and lets patients control access through consent-based sharing.

**All data in this project is synthetic.**

> 🚧 This README is filled in phase by phase. See `docs/PLAN.md` for progress and `docs/SPEC.md` for the full specification.

## Stack
- **Frontend:** Next.js 16 (App Router) · TypeScript · Tailwind v4 · shadcn/ui · TanStack Query
- **Backend:** FastAPI · SQLAlchemy 2 (async) · Alembic · Postgres 16
- **FHIR:** HAPI FHIR JPA server (R4)
- **AI:** Google Gemini (`google-genai`), see `docs/DECISIONS.md`

## Quick start
```bash
cp .env.example .env              # then fill in the keys
docker compose up -d              # Postgres 16 + HAPI FHIR (HAPI takes ~60–90 s to boot)

# Backend (Python 3.11)
cd backend
python3.11 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --reload --port 8000

# Frontend
cd ../frontend
npm install
npm run dev                       # http://localhost:3000
```

Check the services: `curl localhost:8000/api/health` and `curl localhost:8080/fhir/metadata`.
To start over with empty databases, run `docker compose down -v`.

## Google sign-in setup
HealthThread uses the Google Identity Services **ID-token flow**, so no client secret is needed.

1. Open Google Cloud Console → **APIs & Services → OAuth consent screen**. Choose **External**, keep the app in *Testing*, and add your Google account(s) under **Test users**.
2. Go to **APIs & Services → Credentials → Create credentials → OAuth client ID**.
3. Set the application type to **Web application**.
4. Under **Authorized JavaScript origins**, add `http://localhost:3000` and your deployed URL, if you have one. You don't need any redirect URIs.
5. Copy the client ID into `.env` as **both** `GOOGLE_CLIENT_ID` and `NEXT_PUBLIC_GOOGLE_CLIENT_ID`, then restart the backend and frontend.
6. Put your own Google email in `ADMIN_EMAILS` to become an admin on first sign-in.

With `DEMO_MODE=true`, the login page also shows one-click **demo accounts** (Priya, Dr. Meena, Dr. Arjun, Admin). `POST /api/auth/demo` returns 404 when `DEMO_MODE=false`.

## Tests
```bash
cd backend && .venv/bin/pytest          # API + unit tests (uses the healththread_test database)
backend/.venv/bin/python e2e/phase1.py   # browser walkthrough (stack must be running)
```
