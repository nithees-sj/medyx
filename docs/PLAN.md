# HealthThread — Build Plan

The phases come from `docs/SPEC.md` §19. Each phase ends with the same gate:
- backend: `pytest`, `ruff check`, `mypy app`
- frontend: `npm run lint`, `tsc --noEmit`, `npm run build`
- the phase's acceptance checks, run on the live stack
- `git commit -m "phase N: <title>"`

Deviations from the spec are listed in `docs/DECISIONS.md`.

## Phase 0 — Scaffold
- [x] git repo, `.gitignore`, `.env` (gitignored), `.env.example`
- [x] `docs/SPEC.md`, `docs/PLAN.md`, `docs/DECISIONS.md`
- [x] `docker-compose.yml`: postgres:16 (app, `hapi`, `healththread_test` DBs via init SQL) + HAPI FHIR R4 on Postgres
- [x] FastAPI skeleton: config, db, `/api/health` (DB + FHIR checks), CORS, logging
- [x] Alembic baseline
- [x] Next.js App Router + TS + Tailwind + shadcn/ui + TanStack Query; `/api/*` rewrites; base layout + "Demo — synthetic data only" badge
- [x] README skeleton
- [x] ✅ `GET :8080/fhir/metadata` → CapabilityStatement; frontend shows backend health

## Phase 1 — Google OAuth + roles
- [x] SQLAlchemy models + migration for all §6.1 tables
- [x] `POST /api/auth/google`, `GET /api/auth/me`, `POST /api/auth/logout`, session JWT cookie
- [x] `POST /api/auth/demo` (404 when `DEMO_MODE=false`), demo personas
- [x] Onboarding: patient → health profile + FHIR Patient + HealthThread ID; doctor → pending
- [x] `ADMIN_EMAILS` auto-admin; admin verification → FHIR Practitioner
- [x] Guards: `current_user`, `require_role`, `require_verified_doctor`, CSRF header
- [x] Next middleware with `?next=` redirect; `/login`, `/onboarding`, `/admin`, dashboards
- [x] ✅ Auth tests; demo 404 check; unverified doctor gets nothing clinical; (real Google sign-in: ⏳ waiting on a GOOGLE_CLIENT_ID from the product owner)

## Phase 2 — Synthetic data
- [x] `scripts/generate_demo_docs.py` → 9 Rajan + 3 Lakshmi files
- [x] ✅ Visually distinct orgs; legible handwriting

## Phase 3 — Smart Ingest
- [x] Upload API (MIME sniffing, 15 MB / 20 pages, sha256 dedupe)
- [x] Background worker with live stages
- [x] Gemini extraction (structured output) + DEMO_CACHE
- [x] Normalise (LOINC, units, brand → generic), confidence gate, review queue
- [x] Merge rules; FHIR transaction Bundle with Provenance + extensions
- [x] `/export` Bundle
- [x] ✅ One eGFR series of 4 values; 133 µmol/L → 1.50 mg/dL; Provenance everywhere; re-upload skipped; export valid

## Phase 4 — Patient portal core
- [ ] `/app` home + profile switcher; upload with live progress; review queue
- [ ] Timeline, trends, medications, documents viewer, settings
- [ ] ✅ Upload → review → timeline at phone width (Playwright)

## Phase 5 — Safety Engine
- [ ] 5 rules + knowledge JSON; explanations via Gemini; fingerprint idempotency
- [ ] Alerts UI + re-run; `/prescriptions/check`
- [ ] ✅ Rajan exactly 4 alerts, Lakshmi 0; idempotent re-run; rule unit tests

## Phase 6 — Consent Vault + emergency card
- [ ] QR share + claim; access requests; `get_scoped_record()`; revoke/expiry
- [ ] Audit log + FHIR Consent/AuditEvent; notifications
- [ ] Emergency card page, wallet PDF, lock-screen PNG
- [ ] ✅ §10.3 tests; revocation immediate; emergency fields only + owner notified

## Phase 7 — Doctor portal + Copilot
- [ ] Risk-sorted dashboard; workspace tabs; specialty summary
- [ ] SSE chat with citation chips → viewer; drafts → notes
- [ ] Doctor upload; prescribe drawer with live check + override reason + PDF
- [ ] Panel insights (function calling)
- [ ] ✅ Spec §19 Phase 7 prompts

## Phase 8 — Polish and demo readiness
- [ ] Landing page; seed `--reset` / `--stage live`; README; ARCHITECTURE.md; DEMO_SCRIPT.md
- [ ] ✅ Clean-clone run + full demo walkthrough
