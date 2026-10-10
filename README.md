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
