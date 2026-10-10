# HealthThread — Full Build Specification for Claude Code

> **One patient, one record, every hospital — and it catches what no single hospital can see.**

> **Note:** This is the original build specification, kept verbatim as the source of truth.
> Deviations agreed during planning (e.g. **Gemini instead of Claude** for the AI layer) are recorded in `docs/DECISIONS.md`.

You are building **HealthThread**, a full-stack, production-quality hackathon platform that turns scattered medical documents (PDFs, photos, handwritten prescriptions) from many hospitals into one unified, standards-based **FHIR R4** record, detects cross-hospital safety problems, gives doctors a grounded AI copilot with citations, and puts the patient in control of who sees what through consent-based sharing.

The platform has **4 engines** and **2 portals**:

| Engines | Portals |
|---|---|
| 1. Smart Ingest (any document → FHIR) | Patient / family caregiver app |
| 2. Cross-hospital Safety Engine | Doctor portal |
| 3. Clinical Copilot (Ask the Record) | (+ admin console, + public emergency card) |
| 4. Consent Vault (sharing, scopes, audit) | |

Authentication for **everyone** (patients, caregivers, doctors, admins) is **Google OAuth (Sign in with Google)**.

---

## 0. How you must work (read first)

1. Read this entire document before writing any code.
2. Create `docs/PLAN.md` with the phases from Section 19 broken into a checklist. Keep it updated as you go.
3. Build **phase by phase, in order**. After each phase:
   - run backend tests (`pytest`) and the frontend build (`npm run build`), plus lint/type-check;
   - start the stack and verify that phase's **acceptance checks** yourself;
   - fix everything until it passes, then `git commit -m "phase N: <title>"`.
4. Never fake results to make a check pass: no hardcoded AI outputs, no stubbed endpoints left behind, no skipped tests. The **only** allowed fallback is the explicit `DEMO_CACHE` mechanism in Section 7.
5. If a library or API behaves differently from this spec, choose the closest working equivalent, record it in `docs/DECISIONS.md`, and continue. Only stop and ask me when you are truly blocked on something only I can provide (API keys, Google client ID).
6. Secrets live in `.env` (gitignored). Maintain `.env.example` with every variable.
7. Prefer simple, readable, well-structured code over clever abstractions. This app will be demoed live to a jury — reliability beats feature count. Every screen needs loading, empty, and error states.
8. All data in this project is **synthetic**. Show a small "Demo — synthetic data only" badge in the app footer.

---

## 1. Product summary

**Problem.** A patient's history is scattered across PDFs, phone photos, WhatsApp forwards and paper prescriptions from different hospitals, clinics and labs, each using different formats, test names and units. Every new doctor starts blind. Dangerous problems hide in the gaps: the same drug prescribed twice under different brand names, a drug given despite a recorded allergy, a side effect treated as a new disease, kidney function quietly declining across reports from different labs.

**Solution.** HealthThread:
1. reads any medical document and converts it into coded FHIR R4 resources with provenance back to the source page;
2. merges records across hospitals (same test, different names/units → one series);
3. runs a deterministic safety engine across the merged record;
4. gives doctors a specialty-tailored summary and a chat copilot whose every answer cites the source document;
5. lets the patient grant scoped, time-limited access to doctors via QR or request/approve, with a full audit log and a public emergency card.

**Users.**
- **Patient / family caregiver** (e.g. Priya managing her father Rajan's health). One Google account can manage multiple health profiles (self + dependents).
- **Doctor** — verified clinician who sees only patients who granted consent, only within the granted scope.
- **Admin** — verifies doctors; has **no** access to clinical data.
- **Emergency responder** — anonymous, sees only the emergency card via a QR token.

---

## 2. Tech stack (fixed decisions)

**Frontend**
- Latest stable **Next.js (App Router) + TypeScript**
- **Tailwind CSS + shadcn/ui**, lucide-react icons
- **@react-oauth/google** (Google Identity Services button, returns an ID token)
- **TanStack Query** for data fetching
- **vis-timeline** (or a maintained React wrapper) for the medical timeline
- **Recharts** for lab trends and sparklines
- **qrcode.react** for QR codes
- **react-pdf** (PDF.js) for the document viewer with page navigation
- Next.js **rewrites** `/api/*` → FastAPI so auth cookies are same-origin

**Backend**
- **Python 3.11+, FastAPI**, Pydantic v2
- **SQLAlchemy 2 + Alembic**, PostgreSQL 16 for app data
- **httpx** async client for the FHIR server
- **google-auth** for verifying Google ID tokens
- **PyJWT** for session tokens
- **anthropic** Python SDK for Claude
- numpy (trend regression), rapidfuzz (fuzzy matching), PyMuPDF (render PDF pages / page crops), Pillow, python-multipart, slowapi (rate limiting)
- Background processing with FastAPI BackgroundTasks or a simple asyncio worker (no Celery)

**FHIR server**
- **HAPI FHIR JPA server** via Docker (`hapiproject/hapi:latest`), FHIR **R4**, base URL `http://localhost:8080/fhir`
- Configure persistence (its own Postgres DB or an H2 file DB on a mounted volume). Verify data survives `docker compose restart`.

**AI**
- Anthropic Claude API. Model from env `ANTHROPIC_MODEL` (default `claude-sonnet-5-5`; can be set to `claude-opus-5-5`).
- All structured outputs via **tool use with strict JSON schemas**, validated with Pydantic. PDFs sent as document content blocks, images as image content blocks.

**Synthetic data:** reportlab (PDFs) + Pillow (handwritten-style prescription images).

**Infra:** `docker-compose.yml` runs Postgres + HAPI FHIR (and optionally backend + frontend). Must also run locally with `uvicorn` and `npm run dev`.

---

## 3. Repository layout

```
healththread/
├── docker-compose.yml
├── .env.example
├── README.md
├── docs/
│   ├── PLAN.md
│   ├── DECISIONS.md
│   ├── ARCHITECTURE.md        # include a mermaid architecture diagram
│   └── DEMO_SCRIPT.md
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── db.py
│   │   ├── models/            # SQLAlchemy models
│   │   ├── schemas/           # Pydantic schemas
│   │   ├── routers/           # auth, onboarding, profiles, documents, review, record,
│   │   │                      # alerts, prescriptions, consents, emergency, doctor,
│   │   │                      # chat, insights, notifications, admin
│   │   ├── services/
│   │   │   ├── fhir_client.py
│   │   │   ├── ingest/        # extract.py, normalize.py, merge.py, pipeline.py
│   │   │   ├── safety/        # engine.py, rules/*.py, explain.py
│   │   │   ├── copilot/       # digest.py, chat.py, summary.py, insights.py
│   │   │   ├── consent.py     # get_scoped_record() lives here
│   │   │   ├── audit.py
│   │   │   └── notifications.py
│   │   ├── ai/
│   │   │   ├── client.py      # the ONLY place that calls the Claude API
│   │   │   └── prompts/       # *.md prompt templates
│   │   └── knowledge/         # loinc_map.json, brand_generic.json, allergy_classes.json,
│   │                          # cascades.json, interactions.json, drift_rules.json
│   ├── demo_cache/            # cached extraction JSON keyed by file sha256
│   ├── scripts/
│   │   ├── generate_demo_docs.py
│   │   └── seed_demo.py
│   ├── tests/
│   └── alembic/
├── frontend/
│   ├── app/                   # routes (see Sections 11–14)
│   ├── components/
│   └── lib/
├── demo_data/                 # generated synthetic documents
└── storage/                   # uploaded files (gitignored)
```

---

## 4. Authentication — Google OAuth

### 4.1 Sign-in flow (ID-token flow, no client secret needed)
1. `/login` shows **"Continue with Google"** using `GoogleLogin` from `@react-oauth/google` inside `GoogleOAuthProvider` (client ID from `NEXT_PUBLIC_GOOGLE_CLIENT_ID`).
2. On success the frontend receives a Google **ID token** (`credential`) and sends `POST /api/auth/google { credential }`.
3. Backend verifies it with `google.oauth2.id_token.verify_oauth2_token(credential, google.auth.transport.requests.Request(), GOOGLE_CLIENT_ID)`. Reject if `email_verified` is false or the audience doesn't match.
4. Upsert the user by Google `sub`; store email, name, picture; update `last_login_at`.
5. Issue a session JWT (HS256, `JWT_SECRET`, 8-hour expiry) in an **httpOnly** cookie `ht_session` (`SameSite=Lax`, `Secure` when not localhost). Payload: `user_id`, `role`, `onboarded`.
6. If the user has no role yet → redirect to `/onboarding`. Otherwise → `/app` (patient), `/doctor` (doctor), `/admin` (admin).
7. Endpoints: `POST /api/auth/google`, `GET /api/auth/me`, `POST /api/auth/logout`.

### 4.2 Onboarding (first login)
- **Choose a role:** "I'm a patient or family caregiver" / "I'm a doctor".
- **Patient / caregiver:** confirm name (prefilled from Google), then create the first **health profile**: for myself or for someone I care for (name, DOB, sex, blood group, relationship, emergency contact name/phone). Creating a profile creates a FHIR `Patient` resource and a human-friendly **HealthThread ID** (e.g. `HT-7K2P-9QX4`). More profiles (dependents) can be added later.
- **Doctor:** full name, specialty (dropdown), hospital/clinic, medical council name, registration number (format validation). Status becomes `pending`. Until an admin verifies them, the doctor sees an "Awaiting verification" dashboard with no patient access. On verification, create a FHIR `Practitioner` resource linked to the user.
- **Admin:** any Google email listed in `ADMIN_EMAILS` becomes admin automatically on first login.

### 4.3 Route protection
- FastAPI dependencies: `current_user`, `require_role("patient" | "doctor" | "admin")`, `require_verified_doctor`.
- Next.js `middleware.ts` redirects unauthenticated users from protected routes to `/login?next=<path>` and returns them afterwards. **This is essential for the QR share flow** (doctor scans QR → signs in with Google → lands back on the claim page).
- CSRF: SameSite=Lax cookie **plus** a required custom header (`X-HT-Request: 1`) on all state-changing requests.

### 4.4 Demo mode (for reliable live judging)
- When `DEMO_MODE=true`, the login page also shows a clearly labeled **"Demo accounts"** panel with one-click logins: **Priya (caregiver)**, **Dr. Meena Raghavan (verified nephrologist)**, **Dr. Arjun Mehta (unverified GP)**, **Admin**.
- `POST /api/auth/demo { persona }` issues a normal session for the seeded user. This endpoint must return **404 when `DEMO_MODE` is false**.
- Real Google sign-in must work alongside demo mode.

### 4.5 Google Cloud setup (document in README)
Google Cloud Console → APIs & Services → Credentials → **Create OAuth client ID** → type **Web application** → Authorized JavaScript origins: `http://localhost:3000` (plus the deployed URL). Configure the OAuth consent screen (External, testing, add test users). Put the client ID in both `GOOGLE_CLIENT_ID` and `NEXT_PUBLIC_GOOGLE_CLIENT_ID`.

---

## 5. Roles, scopes and permissions

| Actor | Can do |
|---|---|
| Patient account owner | Full read/write on own health profiles (self + dependents); upload; review; manage consents; view audit log; emergency card; export record |
| Verified doctor | Only profiles with an **active, unexpired** consent; only resource categories inside the granted scopes; upload documents / write prescriptions / add notes **only if** `can_write` is granted; review alerts; chat; panel insights over consented patients |
| Unverified doctor | Nothing clinical |
| Admin | Verify/reject doctors; view aggregate stats; **no clinical data access** |
| Emergency viewer (anonymous) | Emergency card fields only |

**Consent scopes** (map FHIR resources to these): `conditions`, `medications`, `allergies`, `labs`, `documents`, `notes`, `mental_health` (sensitive — off by default). Demographics (name, age, sex) are always included in any consent.

---

## 6. Data model

### 6.1 PostgreSQL (app data)
- `users` — id (uuid), google_sub (unique), email, name, avatar_url, role (`patient|doctor|admin`, nullable until onboarding), created_at, last_login_at
- `doctor_profiles` — user_id (PK/FK), full_name, specialty, organization, council, registration_number, verification_status (`pending|verified|rejected`), verified_by, verified_at, review_note, fhir_practitioner_id
- `health_profiles` — id, owner_user_id, display_name, relationship (`self|parent|child|spouse|other`), fhir_patient_id, dob, sex, blood_group, emergency_contact_name, emergency_contact_phone, healththread_id (unique), record_version (int, bump on any record change), created_at
- `documents` — id, profile_id, uploaded_by_user_id, uploader_role, original_filename, mime, storage_path, sha256, page_count, status (`queued|processing|needs_review|done|failed`), stage (current pipeline stage label), error, fhir_document_reference_id, source_org_name, document_date, created_at
- `extraction_items` — id, document_id, resource_type, payload (jsonb), confidence, page, source_snippet, review_status (`auto_accepted|pending|confirmed|corrected|rejected`), fhir_resource_id
- `alerts` — id, profile_id, rule_id, type (`duplicate_therapy|allergy_conflict|prescribing_cascade|lab_drift|interaction`), severity (`info|warning|critical`), title, patient_text, clinical_text, evidence (jsonb list of FHIR resource refs + document/page), status (`active|reviewed_intentional|resolved|dismissed`), reviewed_by, review_note, fingerprint (unique), created_at, updated_at
- `consents` — id, profile_id, granted_by_user_id, doctor_user_id (nullable until claimed), scopes (text[]), can_write (bool), purpose, status (`pending_claim|requested|active|revoked|expired|denied`), share_token_hash, claim_deadline, duration_hours, expires_at, fhir_consent_id, created_at, revoked_at
- `audit_events` — id, profile_id, actor_user_id (nullable), actor_label, action (`view|upload|prescribe|chat|summary|export|emergency_view|consent_change|alert_review`), scopes_touched, details (jsonb), ip, created_at
- `emergency_cards` — profile_id (PK), token_hash, enabled, created_at, regenerated_at
- `chat_messages` — id, profile_id, doctor_user_id, role (`user|assistant`), content, citations (jsonb), created_at
- `clinical_notes` — id, profile_id, author_user_id, title, body, fhir_document_reference_id, created_at
- `notifications` — id, user_id, type, title, body, link, read_at, created_at
- `summary_cache` — profile_id, specialty, record_version, content (jsonb), created_at

### 6.2 FHIR R4 resources (stored in HAPI)
Per health profile: `Patient`, `Organization` (one per source hospital/lab), `Practitioner`, `Encounter`, `Condition`, `Observation` (labs, LOINC-coded, `valueQuantity` in canonical UCUM units), `MedicationRequest`, `AllergyIntolerance`, `DiagnosticReport`, `DocumentReference` (one per uploaded file and per doctor-authored note), `Provenance`, `Consent`, `AuditEvent`.

- **Provenance:** every extracted resource gets a Provenance whose `entity` references the source `DocumentReference` and whose `agent` is the uploader. Record the source page number with an extension.
- **Extensions** (base URL `https://healththread.app/fhir/StructureDefinition/`): `source-page`, `brand-name`, `extraction-confidence`, `written-text` (verbatim text as written on the document).
- Write to HAPI using **transaction Bundles**. Validate resources before sending (fhir.resources R4B models or HAPI's `$validate`).
- `GET /api/profiles/{id}/export` returns the full record as a FHIR `Bundle` (type `collection`) — the interoperability proof point.

---

## 7. Engine 1 — Smart Ingest (any document → FHIR)

**Who can upload:** the patient account owner, or a doctor whose consent has `can_write`.

**Pipeline** (each stage updates `documents.stage` so the UI can show live progress):

1. **Upload** — PDF / JPG / PNG (HEIC optional). Max 15 MB, max 20 pages. Store with a random filename in `storage/`. Compute sha256; skip duplicates of the same file for the same profile.
2. **Extract (AI)** — one Claude call per document using a `record_extraction` tool with a strict JSON schema:
   - `document`: type (`prescription|lab_report|discharge_summary|opd_note|imaging_report|other`), source_organization {name, address?}, practitioner {name, specialty?}, document_date, encounter_reason
   - `conditions[]`: text, icd10_guess, onset_date?, clinical_status, page, snippet, confidence
   - `medications[]`: written_text (verbatim), brand?, generic_molecule, strength, form, frequency_text (e.g. `1-0-1`), frequency_parsed {morning, afternoon, night, per_day}, duration_days?, route, start_date, instructions?, page, snippet, confidence
   - `allergies[]`: substance, reaction?, criticality?, recorded_date?, page, snippet, confidence
   - `labs[]`: test_name_as_written, value, unit_as_written, reference_range_text?, flag_as_written?, specimen_date, page, snippet, confidence
   - `vitals[]` (optional): name, value, unit, date
   The prompt must teach Indian prescription conventions: `1-0-1` = morning–afternoon–night; `Tab.`/`Cap.`/`Syp.`; `OD`, `BD`, `TDS`, `HS`, `SOS`; "x 5 days".
3. **Normalize (deterministic Python, not AI)**
   - Lab names → LOINC via `knowledge/loinc_map.json` (aliases per code) with rapidfuzz fallback; unknown tests keep their text without a code. Seed at least:
     - `2160-0` Creatinine (serum/plasma) — aliases: "S. Creatinine", "Creatinine, Serum", "Serum creatinine", "Creatinine"
     - `33914-3` eGFR — aliases: "eGFR", "Estimated GFR (CKD-EPI)", "GFR, estimated", "eGFR (MDRD)"
     - `4548-4` HbA1c — aliases: "HbA1c", "Glycated haemoglobin", "Glycosylated Hb"
     - `1558-6` Fasting glucose — aliases: "FBS", "Fasting blood sugar", "Glucose fasting"
     - `2823-3` Potassium (serum/plasma)
     - `718-7` Hemoglobin (blood)
     - `3016-3` TSH
   - Units → canonical: creatinine µmol/L → mg/dL (÷ 88.4); glucose mmol/L → mg/dL (× 18.0); HbA1c mmol/mol → % (0.09148 × value + 2.152).
   - Brand → generic via `knowledge/brand_generic.json`, falling back to Claude's `generic_molecule`. Keep the brand in the `brand-name` extension. Seed at least: Glycomet → metformin, Glucophage → metformin, Cardace → ramipril, Ecosprin → aspirin, Novamox → amoxicillin, Mox → amoxicillin, Dolo 650 → paracetamol, Crocin → paracetamol, Amlong → amlodipine, Thyronorm → levothyroxine. Each entry includes a drug class (e.g. ramipril → `ace_inhibitor`, amoxicillin → `penicillin`).
   - Medications with a duration get a bounded timing and become `completed` after the end date; chronic meds without a stop date stay `active`.
4. **Confidence gate** — items with confidence < 0.80 (or flagged uncertain) become `pending` in the **Review queue**; others are auto-accepted. Pending items are not written to FHIR until confirmed or corrected.
5. **Merge / deduplicate** against the existing record:
   - Observation: same LOINC + same date (±1 day) + value within 2% → one Observation with an extra Provenance.
   - MedicationRequest: same generic + same organization + same start date → merge.
   - Condition: same ICD-10 code → one Condition, extra Provenance.
   - Organization: fuzzy name match.
6. **Write** — one FHIR transaction Bundle per document (DocumentReference + resources + Provenance). Store returned IDs, bump `record_version`.
7. **Trigger the Safety Engine** for the profile.
8. **DEMO_CACHE** — after a successful extraction, save the raw extraction JSON to `backend/demo_cache/<sha256>.json`. If the Claude API call fails and `DEMO_CACHE=true`, use the cached result **only for files whose hash is already cached** (so the live demo survives network failure). Unknown files must fail visibly, never silently.

**Frontend stage labels:** Uploading → Reading document → Extracting with AI → Normalising codes & units → Merging with existing record → Saving to FHIR → Running safety checks → Done (with counts: "3 conditions, 5 medicines, 12 lab values").

---

## 8. Engine 2 — Cross-hospital Safety Engine

**Principle:** rules decide whether an alert fires (deterministic, testable). Claude only writes the explanations. Alerts are decision support, never orders.

**Runs on:** every completed ingest, every prescription draft check, and a manual "Re-run checks" button.

**Rules** (knowledge in JSON, evaluators in Python):

1. **duplicate_therapy** — ≥ 2 active MedicationRequests with the same generic molecule (or two drugs from the same listed class, e.g. two ACE inhibitors). Severity `warning`.
2. **allergy_conflict** — an AllergyIntolerance substance/class vs any MedicationRequest (active or historic) whose molecule is in that class (`knowledge/allergy_classes.json`; penicillins: amoxicillin, ampicillin, cloxacillin, piperacillin, penicillin V, penicillin G, co-amoxiclav). Severity `critical`.
3. **prescribing_cascade** — `knowledge/cascades.json` entries `{index_class, adverse_effect, marker_class, window_days}`. Fire when a marker drug starts within the window after an index drug that is still active. Seed:
   - ACE inhibitor → dry cough → antitussive / cough syrup (dextromethorphan, codeine linctus), 180 days
   - Dihydropyridine CCB (amlodipine) → ankle oedema → loop diuretic (furosemide, torsemide), 180 days
   - NSAID → raised blood pressure → antihypertensive, 90 days
   - Metoclopramide → parkinsonism → levodopa, 365 days
   - Cholinesterase inhibitor → urinary incontinence → anticholinergic (oxybutynin), 365 days
   Severity `warning`.
4. **lab_drift** — `knowledge/drift_rules.json` per analyte (eGFR, creatinine, HbA1c, hemoglobin, potassium): bad direction, minimum slope per year, threshold. Requires ≥ 3 points spanning ≥ 180 days. Fit a linear regression (`numpy.polyfit`) on value vs time; fire if the slope goes the bad direction beyond the minimum **even when every value is inside the reference range**. Compute the projected date of crossing the threshold.
   - **Drug–lab combination:** metformin active AND (eGFR < 45 OR projected to cross 45 within 12 months) → "review metformin dose"; eGFR < 30 → `critical`.
5. **interaction** — small curated `knowledge/interactions.json`: ACE inhibitor/ARB + spironolactone or potassium supplement → hyperkalaemia; warfarin + NSAID/aspirin → bleeding; clarithromycin + simvastatin → myopathy; SSRI + tramadol → serotonin syndrome.

**Alert record:** title, `patient_text` (plain language, short, ends with "Please discuss this with a doctor before changing any medicine."), `clinical_text` (concise, with dates and sources), evidence (FHIR refs + document + page so the UI can open the source). `fingerprint = hash(rule_id + sorted evidence ids)` keeps re-runs idempotent. If a doctor marks an alert **reviewed — intentional** with a note, it stays suppressed unless its evidence changes.

**Prescribe-time check:** `POST /api/profiles/{id}/prescriptions/check { drug, strength, frequency, duration }` runs all rules against the record **plus the draft** and returns the alerts that would fire, before anything is saved.

**False-positive control:** a second synthetic patient (Lakshmi, Section 15) must produce **zero** alerts.

---

## 9. Engine 3 — Clinical Copilot (Ask the Record)

### 9.1 Record digest (shared by all copilot features)
`build_digest(profile_id, scopes)` fetches FHIR resources **through `get_scoped_record()` only** and serialises them as compact lines, each with a stable citation key, e.g.:
`[Observation/123] 2026-08-05 eGFR 47 mL/min/1.73m² (Medline Path Labs, doc D9 p1)`
Include active alerts. If the digest would exceed ~150k tokens, drop the oldest Observations first and note the truncation.

### 9.2 Doctor chat (per patient)
- `POST /api/profiles/{id}/chat` with **SSE streaming**; history stored in `chat_messages`.
- System prompt rules: answer **only** from the digest; cite every factual claim with its `[Type/id]` key; if something isn't in the record, say so; no diagnoses or treatment orders (may list considerations for the clinician); absolute dates; concise.
- Frontend renders citation keys as clickable chips → opens the document viewer at the source page with the snippet highlighted (search the snippet text on that page; fall back to a highlighted snippet box).
- Quick-prompt chips: "Summarise the last 6 months", "All medication changes with reasons", "Any safety concerns?", "Draft a referral letter to cardiology".
- Drafts (letters, visit summaries) open in an editable panel; the doctor can save as a clinical note (stored + FHIR DocumentReference authored by the doctor's Practitioner). Requires `can_write`.

### 9.3 Specialty summary
`GET /api/profiles/{id}/summary?specialty=nephrology` → cached in `summary_cache` per (profile, specialty, record_version). Fixed sections: Key problems · Current medications · Relevant labs (with trend arrows) · Active alerts · Open questions for this visit. Every line cited.

### 9.4 Panel insights (doctor dashboard)
`POST /api/doctor/insights { question }`. Claude answers using **tools only** (no free-form SQL/FHIR queries):
`list_patients_with_lab_trend(loinc, direction, min_points)`, `list_patients_on_drug(molecule_or_class)`, `list_patients_with_alert(type, severity)`, `get_latest_lab(loinc)`.
Tools execute only over this doctor's actively consented profiles and scopes. Return a ranked table with sparkline data. Example: "Which of my patients have declining kidney function?"

### 9.5 Patient-side explainer (bonus)
On the patient portal: "Explain this report in simple words" with a language selector (English, Tamil, Hindi). Same grounding and citation rules.

---

## 10. Engine 4 — Consent Vault

### 10.1 Share by QR (patient → doctor)
1. Patient picks a profile → **Share with a doctor** → scope checkboxes (default: conditions, medications, allergies, labs; `mental_health` off), duration (24 h / 7 days / 30 days), toggle "Allow doctor to add documents & prescriptions" (`can_write`).
2. Backend creates a consent with status `pending_claim` and a random 32-byte token (store only its hash). QR encodes `APP_BASE_URL/share/<token>`; it must be claimed within **15 minutes**.
3. Doctor scans → `/share/<token>` → if not signed in → Google sign-in → back to the claim page → must be a **verified doctor** → claim binds `doctor_user_id`, status `active`, `expires_at = now + duration`. The patient gets a notification.

### 10.2 Access request (doctor → patient)
Doctor searches by **exact** HealthThread ID or the account owner's exact email (no fuzzy search, to prevent enumeration) → creates a `requested` consent with proposed scopes and duration → patient sees a request card (doctor name, specialty, verified badge) → approve (can reduce scopes/duration) or deny.

### 10.3 Enforcement (most important security rule)
A single function `get_scoped_record(profile_id, viewer)` in `services/consent.py` that **every** doctor-facing endpoint must use (workspace, timeline, trends, documents, summary, chat, insights, prescriptions). It checks the consent is active and unexpired and filters resources by scope. Write tests proving:
- out-of-scope resources are never returned (including inside chat context);
- expired consent → 403; revoked consent → 403 immediately;
- unverified doctor → 403; admin → 403 on clinical endpoints.

### 10.4 Revoke, expiry, audit
- Patient can revoke any active consent instantly; the doctor's next request fails and the patient disappears from their dashboard.
- Expiry is checked at request time (plus periodic cleanup).
- Every doctor view / chat / summary / upload / prescription / alert review and every emergency view writes an `audit_events` row. Patient **Access log** shows entries like "Dr. Meena Raghavan (Nephrology) viewed labs and medications — 10:42 AM". Mirror consents and audit events to HAPI as FHIR `Consent` and `AuditEvent` resources.
- In-app notifications with a bell icon (email optional).

---

## 11. Patient portal (mobile-friendly)

| Route | Purpose |
|---|---|
| `/` | Landing page: pitch, how it works (3 steps), "Continue with Google" |
| `/login`, `/onboarding` | Section 4 |
| `/app` | Home with **profile switcher** (e.g. "Me", "Appa — Rajan"); cards: active alerts, recent documents, quick actions (Upload, Share, Emergency card) |
| `/app/p/[id]/upload` | Drag-and-drop multi-file upload with live per-file stage progress and result counts |
| `/app/p/[id]/review` | Review queue: page crop + snippet + editable fields → confirm / correct / reject |
| `/app/p/[id]/timeline` | vis-timeline with lanes: Conditions, Medications (start→stop bars), Labs (points), Documents; coloured by source organization; click → drawer with source citation |
| `/app/p/[id]/trends` | Per-analyte charts: reference band shading, points coloured by lab, regression line + dashed projection when a drift alert exists |
| `/app/p/[id]/alerts` | Patient-friendly alert cards + "Show this to my doctor" (opens share flow) |
| `/app/p/[id]/medications` | Current list (generic + brand), source, start date; mark as stopped |
| `/app/p/[id]/documents` | All files, filter by hospital/type, viewer |
| `/app/p/[id]/sharing` | Active consents (doctor, scopes, expiry, revoke), pending requests, create QR share |
| `/app/p/[id]/access-log` | Audit timeline |
| `/app/p/[id]/emergency` | Enable, preview, print wallet card, download lock-screen image, regenerate/disable |
| `/app/settings` | Manage profiles/dependents, export record as FHIR Bundle, sign out |

---

## 12. Doctor portal (desktop-first)

| Route | Purpose |
|---|---|
| `/doctor` | Verification banner if pending. **Panel insights** box at top. Patient list (active consents) sorted by critical alerts → warnings → recent uploads; columns: name, age, alert badges, access expires, last activity. Pending outgoing requests. |
| `/doctor/patients/[id]` | **Patient workspace**: tabs for Summary (specialty-tailored, specialty selector defaults to the doctor's own), Timeline, Trends, Alerts (mark "reviewed — intentional" with note / resolve), Medications, Documents (viewer + upload if `can_write`), Notes. A persistent **chat panel** on the right. |
| Prescribe drawer | Drug search (brand_generic.json + free text), strength, frequency picker (`1-0-1` style), duration, instructions. **Live safety check** as the doctor types (debounced call to `/prescriptions/check`), alerts shown inline. Saving over a `critical` alert requires an override reason (stored in audit + MedicationRequest note). Creates a FHIR MedicationRequest authored by the doctor's Practitioner; printable prescription PDF. Requires `can_write`. |
| `/doctor/requests` | Search by HealthThread ID / email and request access |
| `/doctor/profile` | Professional details and verification status |

---

## 13. Admin console
`/admin`: pending doctor verifications (approve/reject with note, notify the doctor), aggregate counts (users, profiles, documents processed, alerts by type). Admin cannot open any patient record.

---

## 14. Emergency card (public)
- Patient enables it per profile → token (hash stored) → QR, a printable **credit-card-size wallet card PDF**, and a **lock-screen PNG** (QR + name + blood group).
- `/emergency/<token>` — no login. Shows only: name, age, sex, blood group, **allergies (prominent, red)**, active medications, active conditions, emergency contact (tap to call), last updated. No labs, no documents.
- Every view → `emergency_view` audit event + notification to the owner ("Emergency access to Rajan's card at 9:14 PM"). Rate-limited by IP. Regenerating the token kills the old QR.

---

## 15. Synthetic demo data (the demo story)

`python -m scripts.generate_demo_docs` writes visually distinct documents to `demo_data/`. `python -m scripts.seed_demo [--reset]` (requires `DEMO_MODE=true`) creates demo users and profiles, ingests all documents **through the real pipeline** (populating `demo_cache`), and creates an active consent Priya → Dr. Meena (7 days, all scopes except mental_health, `can_write=true`) so the doctor dashboard is populated. All names and organizations are fictional.

**People**
- Patient: **Rajan Subramanian**, male, DOB 1962-05-14, blood group B+
- Caregiver account: **Priya Rajan** (daughter) — owns Rajan's profile
- Verified doctor: **Dr. Meena Raghavan**, Nephrology
- Unverified doctor: **Dr. Arjun Mehta**, General Medicine
- Control patient: **Lakshmi Iyer**, female, 58, hypothyroidism — clean record

**Organizations** (each with its own visual style)
- **Sunrise Diabetes & Multispeciality Hospital** — formal typed letterhead, blue
- **Anand Family Clinic** — handwritten prescriptions on a printed pad (images; handwriting-style font such as Caveat, slight rotation, paper texture, a bit of noise)
- **Lakeview Heart Institute** — modern two-column layout, red
- **City Diagnostics** — table-style lab report
- **Medline Path Labs** — lab report in SI units

**Rajan's documents**

| # | File | Content |
|---|---|---|
| 1 | `sunrise_2024-03-12_opd.pdf` | Dr. K. Srinivasan (Diabetology). Dx: Type 2 diabetes mellitus. **Allergy: Penicillin — skin rash (2022).** Rx: Tab. Glycomet 500 mg 1-0-1 after food, continue. |
| 2 | `sunrise_2024-03-12_lab.pdf` | HbA1c 7.8 %; Fasting blood sugar 156 mg/dL; Serum creatinine 1.0 mg/dL; eGFR 72 mL/min/1.73m² |
| 3 | `lakeview_2025-01-20_cardiology.pdf` | Dr. S. Fernandes (Cardiology). Dx: Essential hypertension, BP 158/96. Rx: Tab. Cardace 5 mg 1-0-0; Tab. Ecosprin 75 mg 0-1-0 after lunch. (No mention of Glycomet — realistic gap.) |
| 4 | `lakeview_2025-01-20_lab.pdf` | Creatinine, Serum 1.2 mg/dL; Estimated GFR (CKD-EPI) 61; HbA1c 7.2 %; Potassium 4.6 mmol/L |
| 5 | `anand_2025-04-02_rx.png` | Dr. R. Anand (GP). C/o dry cough × 6 weeks. Rx: Syp. Dextromethorphan 10 ml 1-1-1 × 7 days |
| 6 | `anand_2025-09-10_rx.png` | C/o tiredness, high sugars. Rx: Tab. Glucophage 500 mg 1-0-1 |
| 7 | `citydx_2026-01-15_lab.pdf` | S. Creatinine 1.4 mg/dL; GFR, estimated 52; HbA1c 7.0 % |
| 8 | `anand_2026-02-18_rx.png` | C/o sore throat, fever. Rx: Cap. Novamox 500 mg 1-1-1 × 5 days; Tab. Dolo 650 SOS |
| 9 | `medline_2026-08-05_lab.pdf` | Creatinine **133 µmol/L** (SI units); eGFR 47 mL/min/1.73m²; Potassium 5.0 mmol/L |

**Lakshmi's documents (control):** 3 documents from one hospital: Dx hypothyroidism; Tab. Thyronorm 50 mcg 1-0-0 before breakfast; TSH 2.1 / 2.4 / 1.9 mIU/L over 18 months.

**Expected safety results — these are acceptance tests**
Rajan must produce **exactly these 4 alerts**:
1. `duplicate_therapy` (warning) — metformin: Glycomet (Sunrise, 2024-03-12) + Glucophage (Anand, 2025-09-10)
2. `allergy_conflict` (critical) — penicillin allergy (Sunrise) vs Novamox → amoxicillin (Anand, 2026-02-18)
3. `prescribing_cascade` (warning) — Cardace → ramipril (ACE inhibitor, Lakeview, 2025-01-20) → dry cough → dextromethorphan (Anand, 2025-04-02)
4. `lab_drift` + metformin (warning) — eGFR 72 → 61 → 52 → 47 across 4 labs with 3 different test names and one report in SI units; projected to cross 45 soon; metformin still active → review dose

Lakshmi must produce **zero** alerts. Creatinine 133 µmol/L must appear as **1.50 mg/dL** in the merged creatinine series. All four eGFR values must appear in **one** LOINC-coded series.

---

## 16. AI implementation rules
- `app/ai/client.py` is the only module that calls Claude. Prompts live in `app/ai/prompts/*.md`.
- Every structured output uses tool use with a JSON schema; validate with Pydantic; on validation failure retry once with the error message, then fail visibly.
- Use low temperature for extraction where the model supports it; set timeouts; log token usage (never log PHI).
- Only send data the current viewer is allowed to see. Doctor-facing prompts must be built from `get_scoped_record()` output.
- Safety alerts are decided by rules; Claude writes explanations only.
- Copilot answers must be grounded and cited; uncited claims are a bug.

---

## 17. Security and safety
- httpOnly session cookie, role guards on every router, CSRF header check.
- Uploaded files stored outside any public folder, served only through an authorized endpoint that runs the consent check.
- MIME sniffing + size/page limits on uploads.
- Rate limiting (slowapi) on auth, emergency, share-claim and AI endpoints.
- No PHI in logs. CORS restricted to `APP_BASE_URL`.
- Store times in UTC; display in the user's timezone (default Asia/Kolkata).
- Disclaimers: alerts and copilot are decision support; the app never instructs patients to stop or change medicines.

---

## 18. UI / UX direction
- Calm, trustworthy clinical look — not a generic gradient SaaS template. Neutral surfaces, one deep teal primary colour; red reserved for critical, amber for warnings, green for confirmed/resolved.
- Each source organization gets a consistent colour used in the timeline, document chips and trend points — this visually sells "many hospitals, one record".
- Clean sans-serif typography, generous whitespace, clear hierarchy, subtle motion only.
- Patient portal must be fully usable on a phone (upload from camera, QR share, emergency card). Doctor portal is desktop-first with a split layout (workspace + chat).
- Skeleton loaders, toasts, empty states with helpful CTAs, accessible contrast and keyboard focus states.

---

## 19. Build phases and acceptance checks

**Phase 0 — Scaffold**
Monorepo, docker-compose (Postgres + HAPI), FastAPI skeleton with `/api/health`, Next.js app with rewrites, Alembic, base layout, `.env.example`, README skeleton.
✅ `docker compose up` starts Postgres + HAPI; `GET http://localhost:8080/fhir/metadata` returns a CapabilityStatement; frontend shows backend health through `/api/health`.

**Phase 1 — Google OAuth + roles**
Google sign-in, session cookie, `/me`, logout, onboarding (patient profile creation → FHIR Patient; doctor profile → pending), admin via `ADMIN_EMAILS`, admin verification screen, route guards, Next middleware with `next` redirect, demo mode personas.
✅ Real Google sign-in works on localhost. New user → onboarding → correct dashboard. Unverified doctor sees no patient data. Demo endpoint returns 404 with `DEMO_MODE=false`. Auth tests pass.

**Phase 2 — Synthetic data**
`generate_demo_docs.py` for Rajan and Lakshmi exactly as in Section 15.
✅ 9 + 3 files generated; each organization visually distinct; handwritten images look handwritten but are legible.

**Phase 3 — Smart Ingest**
Upload API, background pipeline with stages, Claude extraction, normalization, confidence gate + review queue, merge, FHIR transaction write with Provenance, DEMO_CACHE.
✅ Ingesting Rajan's 9 documents produces one merged record; all eGFR values in one LOINC series; 133 µmol/L stored as 1.50 mg/dL; brands mapped to generics; every resource has Provenance to its document and page; re-uploading the same file is skipped; `/export` returns a valid Bundle.

**Phase 4 — Patient portal core**
Home with profile switcher, upload with live progress, review queue, timeline, trends, medications, documents viewer.
✅ Priya can complete the whole upload → review → timeline flow on a phone-width screen.

**Phase 5 — Safety Engine**
All 5 rule types, knowledge JSON files, Claude explanations, alerts UI, re-run, prescribe-time check endpoint.
✅ Rajan gets **exactly** the 4 expected alerts; Lakshmi gets zero; re-running creates no duplicates; unit tests for every rule (positive and negative cases).

**Phase 6 — Consent Vault + emergency card**
QR share + claim with Google sign-in redirect, access requests, `get_scoped_record()`, revoke/expiry, audit log + FHIR Consent/AuditEvent mirroring, notifications, emergency card (page, wallet PDF, lock-screen PNG).
✅ All consent enforcement tests in 10.3 pass; revocation takes effect on the next request; emergency page shows only allowed fields and notifies the owner.

**Phase 7 — Doctor portal + Copilot**
Dashboard sorted by risk, patient workspace, specialty summary, chat with SSE + citation chips → document viewer, drafts → notes, doctor upload, prescribe drawer with live safety check and override reason, panel insights with tools.
✅ Dr. Meena asks "When did kidney function start declining and what was he taking then?" and gets a cited answer whose chips open the right pages. Typing "Novamox 500" in the prescribe drawer shows the penicillin allergy alert before saving. "Which of my patients have declining kidney function?" returns Rajan with a sparkline and not Lakshmi.

**Phase 8 — Polish and demo readiness**
Landing page, seed script with `--reset`, README (setup, Google Cloud steps, env vars, run commands, architecture diagram), `docs/DEMO_SCRIPT.md`, consistent loading/empty/error states, final test run.
✅ From a clean clone: copy `.env.example` → `.env`, fill keys, `docker compose up`, run migrations + seed, open the app, and the full demo (Section 21) works end to end.

---

## 20. Environment variables

```
# Auth
GOOGLE_CLIENT_ID=
NEXT_PUBLIC_GOOGLE_CLIENT_ID=
JWT_SECRET=
ADMIN_EMAILS=you@gmail.com

# AI
ANTHROPIC_API_KEY=
ANTHROPIC_MODEL=claude-sonnet-5-5

# Data
DATABASE_URL=postgresql+psycopg://healththread:healththread@localhost:5432/healththread
FHIR_BASE_URL=http://localhost:8080/fhir
STORAGE_DIR=./storage

# App
APP_BASE_URL=http://localhost:3000
DEMO_MODE=true
DEMO_CACHE=true
DEFAULT_TIMEZONE=Asia/Kolkata
```

---

## 21. Demo script (3 minutes — put this in `docs/DEMO_SCRIPT.md`)
1. **Patient (Priya, phone):** sign in with Google → Rajan's profile → upload the 9 messy documents from 5 sources → watch live stage progress → the unified timeline appears, colour-coded by hospital.
2. **Safety:** 4 alerts appear — duplicate metformin, penicillin allergy conflict, ACE-inhibitor cough cascade, silent eGFR decline with metformin. Open the trend chart showing 4 labs merged with a projection line.
3. **Share:** Priya creates a 7-day QR share (labs + medicines + conditions + allergies).
4. **Doctor (Dr. Meena, laptop):** scans the QR → signs in with Google → Rajan appears at the top of her dashboard with 4 alerts → nephrology summary → asks the copilot a question → clicks a citation → the original 2024 lab report page opens.
5. **Prevention:** Dr. Meena starts prescribing Novamox → live allergy alert blocks it → she picks a safe alternative and saves.
6. **Control:** Priya opens the Access log ("Dr. Meena viewed labs…"), then taps **Revoke** → Dr. Meena refreshes → access denied.
7. **Emergency:** scan Rajan's emergency card → allergies, blood group, current meds; Priya receives an emergency-access notification.

---

## 22. Definition of done
- [ ] All phase acceptance checks pass; `pytest` green; `npm run build` clean
- [ ] Google OAuth works for patients, doctors and admins; demo mode works and is disabled when `DEMO_MODE=false`
- [ ] Rajan → exactly 4 alerts; Lakshmi → 0 alerts
- [ ] Every copilot claim is cited and every citation opens the source page
- [ ] Consent scopes are enforced everywhere, including chat and insights
- [ ] Full record export as a FHIR Bundle
- [ ] README lets a new developer run everything from a clean clone
- [ ] The 3-minute demo runs end to end without touching the terminal
