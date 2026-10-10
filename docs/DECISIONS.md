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
`create-next-app` enables `cacheComponents` and `partialPrefetching`. Authenticated screens are client components that fetch through TanStack Query, so they do not read request data on the server. Anything that uses `useSearchParams` sits behind a `<Suspense>` boundary.
