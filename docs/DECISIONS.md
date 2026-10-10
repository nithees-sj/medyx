# Decisions & deviations from the spec

Each entry records where the build differs from `docs/SPEC.md`, or where a choice was left open, and why.

## D1 — Repository root is `medyx/`
The spec shows the tree under `healththread/`. The project lives in the existing `medyx/` folder, so the same layout (`backend/`, `frontend/`, `docs/`, …) sits directly at the repo root.

## D2 — AI provider: Google Gemini instead of Anthropic Claude
The product owner asked for Gemini. Every rule in spec §16 still holds, mapped onto Gemini:

| Spec (Claude) | Implementation (Gemini) |
|---|---|
| `anthropic` SDK, `app/ai/client.py` only caller | `google-genai` SDK (`client.aio.models.generate_content` / `generate_content_stream`); `app/ai/client.py` is still the only module that calls the model |
| `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL` | `GEMINI_API_KEY`, `GEMINI_MODEL` |
| Tool use with strict JSON schema | Structured output: `response_mime_type="application/json"` + `response_json_schema` generated from Pydantic, then `Model.model_validate_json`. A validation failure is retried once with the error message, then fails visibly |
| PDF document blocks / image blocks | `types.Part.from_bytes(data, mime_type="application/pdf" | "image/png" | "image/jpeg")` |
| Tool use for panel insights | Gemini function declarations with automatic function calling **disabled**; we run a manual loop and execute tools server-side over consented data only |
| SSE streaming | `generate_content_stream` → FastAPI `StreamingResponse` (`text/event-stream`) |
| "Low temperature where supported" | `temperature=0.0` + `thinking_level="low"` for extraction (both verified accepted) |

**SDK surface:** `google-genai` 2.29 has both the newer Interactions API (`client.interactions.create`) and `client.models.generate_content`. We use `models.generate_content`: it has typed Pydantic config objects and async support, and it is the surface the SDK documents for structured output, `Part.from_bytes` and function calling.

## D3 — Default model is `gemini-3.5-flash`
On 2026-10-10, `gemini-3.8-flash` (and the `gemini-flash-latest` alias) did not answer a one-word prompt within 90 s (504 DEADLINE_EXCEEDED) for this API key. `gemini-3.5-flash` answered in about 2 s. For a live demo, reliability comes first. The model can be changed with `GEMINI_MODEL`.

## D4 — All databases run in Docker
One `postgres:16-alpine` container serves three databases, created by `docker/postgres/init/01-databases.sql` on first boot:
- `healththread`: app data
- `hapi`: HAPI FHIR JPA persistence
- `healththread_test`: pytest

The HAPI image is distroless (no curl), so its readiness is checked from the backend `/api/health` and not with a container healthcheck.

## D5 — Python 3.11 venv
The host Python is 3.14. The backend uses `~/.pyenv/versions/3.11.9` (spec: "Python 3.11+") so that every scientific/PDF wheel is available.

## D6 — Next.js 16: `proxy.ts` instead of `middleware.ts`
Next.js 16 renamed the Middleware file convention to **Proxy** (`proxy.ts`, `export function proxy`). The behaviour is the same: unauthenticated users on protected routes are redirected to `/login?next=<path>`. The proxy matcher covers page routes only (never `/api/*`), so upload bodies are not buffered by the proxy's 10 MB limit.

## D7 — Next.js 16 Cache Components left at scaffold default
`create-next-app` enables `cacheComponents` and `partialPrefetching`. Authenticated screens are client components that fetch through TanStack Query, so they do not read request data on the server. Anything that uses `useSearchParams` sits behind a `<Suspense>` boundary. Because the authenticated sections only render after a client-side role check, their pages are not prerendered into the static shell. So `experimental.instantInsights.validationLevel` is set to `manual-warning` (validate only segments that opt in), which avoids dev-overlay noise about "dropped" segments.

## D8 — Deterministic synthetic documents
`scripts/generate_demo_docs.py` produces byte-identical files on every run and in every checkout. PDFs are rendered with reportlab's invariant mode into memory (writing by filename would put the path into the PDF `/ID`). Images use seeded RNGs (PIL's `effect_noise` uses an unseeded C RNG, so it was replaced with seeded numpy noise). This keeps `DEMO_CACHE` (keyed by sha256) valid after regeneration.

## D9 — Lakshmi's control documents
The spec asks for "3 documents from one hospital" with TSH 2.1 / 2.4 / 1.9 over 18 months. They are:
- a 2-page OPD note (page 1: consultation with Dx and Thyronorm Rx; page 2: the attached TSH 2.1 report)
- two later TSH-only lab reports

Thyronorm is prescribed only once, so the record contains a single levothyroxine order and no duplicate-therapy false positive. The 2-page note also exercises page-level provenance.

## D10 — Citations can open their source document without the `documents` scope
The demo share grants conditions, medications, allergies and labs, not `documents`. A doctor must still be able to click a citation and see the lab report page it came from. So `get_scoped_record()` exposes two kinds of document:
- **Listable:** documents the doctor's scopes grant (`documents` for uploads, `notes` for clinical notes). These appear in the library.
- **Citable:** documents that are the source (via Provenance) of a resource the doctor can already see. These open only from a citation.

A document that carries a mental-health item the doctor can't see is never citable, so it can't leak hidden information.

## D11 — HAPI search cache disabled
By default HAPI reuses cached results for identical searches for 60 s. The ingest pipeline re-reads the record right after writing it (to merge the next document), so stale searches caused missed merges. Fix:
- every search sends `Cache-Control: no-cache`
- compose sets `hapi.fhir.reuse_cached_search_results_millis: 0`

## D12 — Gemini quota handling
The provided key is on the free tier. Google's 429s showed 5 requests/min and 20 requests/day per model.
- A process-wide sliding-window limiter (`AI_REQUESTS_PER_MINUTE`, default 5) spaces out every call. 429/503 responses are retried after Google's `retryDelay`, waiting longer for background ingestion than for interactive calls.
- `demo_cache/` holds the 12 real extraction results for the 12 synthetic files, keyed by sha256. Eleven came from `gemini-3.5-flash`. The Lakeview lab report came from `gemini-3.5-flash-lite`, because the daily quota was used up while building. When a call fails (for example, quota exhausted), the pipeline falls back to these cached results, exactly as spec §7.8 allows. Unknown files still fail visibly.
- With a paid key, raise `AI_REQUESTS_PER_MINUTE` and the same code runs faster.

## D13 — Year-only allergy dates go to the review queue
The Sunrise note records "Penicillin — skin rash (2022)". The model outputs `2022-01-01` and flags that only the year was given. Per spec §7.4 ("or flagged uncertain"), that item waits in the review queue until a person confirms it, so the penicillin conflict alert appears once Priya confirms. The seed script confirms it through the same review API.

## D14 — Source-organisation colours
Each hospital or lab gets a stable colour per profile, assigned in order of first appearance and used everywhere: timeline, chips, trend points. The 8-slot palette avoids the reserved status colours (red/amber/green) and the teal brand. It passes the dataviz palette validator (lightness band, chroma floor, adjacent-pair colour-vision-deficiency ΔE ≥ 8, normal-vision floor, 3:1 contrast). Colour is never the only cue: every chart has a legend and a table view.

## D15 — Citation highlighting
The viewer renders PDFs with react-pdf (PDF.js) and highlights text-layer items that appear in the quoted snippet on the cited page. If none match, or the source is a photo, a quote box shows the snippet. The review queue uses a server-rendered crop (PyMuPDF `search_for`) with the snippet boxed.
