"""Platform telemetry for the admin console: API requests, AI calls, system events, job health.

Recording never blocks or fails a request: rows go into bounded in-memory buffers and a
background task bulk-inserts them every few seconds. Only metadata is recorded (route
template, status, latency, model, token counts, event kind) — never bodies, prompts,
answers or anything from a patient's record.
"""

import asyncio
import logging
import re
import time
import uuid
from collections import deque
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import delete, insert

from app.config import get_settings
from app.db import SessionLocal, utcnow
from app.models import AICall, RequestLog, SystemEvent

log = logging.getLogger(__name__)

_MAX_BUFFER = 20_000
_requests: deque[dict[str, Any]] = deque(maxlen=_MAX_BUFFER)
_ai_calls: deque[dict[str, Any]] = deque(maxlen=_MAX_BUFFER)
_events: deque[dict[str, Any]] = deque(maxlen=_MAX_BUFFER)
_recent_event_keys: dict[tuple[str, ...], float] = {}
STARTED_AT = utcnow()


@dataclass
class JobStatus:
    runs: int = 0
    last_run: datetime | None = None
    last_ok: bool | None = None
    last_error: str | None = None
    last_result: str | None = None
    interval_seconds: int | None = None
    history: list[bool] = field(default_factory=list)


jobs: dict[str, JobStatus] = {}


def reset() -> None:
    """Clear buffers (tests)."""
    _requests.clear()
    _ai_calls.clear()
    _events.clear()
    _recent_event_keys.clear()


# ───────────────────────────── recording ─────────────────────────────

_ID_SEGMENT = re.compile(r"/(?:[0-9a-fA-F-]{32,36}|\d+|[A-Za-z0-9_-]{20,})(?=/|$|\.)")


def route_template(scope: Mapping[str, Any]) -> str:
    route = scope.get("route")
    path = getattr(route, "path", None)
    if isinstance(path, str):
        # Included routers can report their path without the mount prefix ("/api"); restore it
        # from the real path, which has the same segments after the prefix.
        actual = scope.get("path", "").rstrip("/").split("/")
        tmpl = path.rstrip("/").split("/")
        extra = len(actual) - len(tmpl)
        if extra > 0:
            path = "/".join(actual[: extra + 1]) + path
        return path[:200]
    # Unmatched paths (404s): collapse ids and tokens so they group instead of exploding the table.
    return _ID_SEGMENT.sub("/{id}", scope.get("path", ""))[:200]


def record_request(
    *, method: str, route: str, status: int, duration_ms: int, user_id: Any, role: str | None, error: str | None
) -> None:
    _requests.append(
        {
            "method": method,
            "route": route,
            "status": status,
            "duration_ms": duration_ms,
            "user_id": user_id,
            "role": role,
            "error": error,
            "created_at": utcnow(),
        }
    )


def record_ai_call(
    *,
    purpose: str,
    model: str,
    ok: bool,
    duration_ms: int,
    input_tokens: int | None,
    output_tokens: int | None,
    thought_tokens: int | None,
    error: str | None,
) -> None:
    _ai_calls.append(
        {
            "purpose": purpose[:40],
            "model": model[:80],
            "ok": ok,
            "duration_ms": duration_ms,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "thought_tokens": thought_tokens,
            "error": (error or None) and error[:200],
            "created_at": utcnow(),
        }
    )


def event(
    kind: str,
    message: str,
    *,
    severity: str = "info",
    user_id: uuid.UUID | None = None,
    details: dict[str, Any] | None = None,
    ip: str | None = None,
    dedupe: tuple[str, ...] | None = None,
    dedupe_seconds: float = 600,
) -> None:
    """Queue a system event. With `dedupe`, repeats of the same key within the window are dropped
    (e.g. a doctor's page polling after access was revoked shouldn't log hundreds of denials)."""
    if dedupe is not None:
        key = (kind, *dedupe)
        now = time.monotonic()
        last = _recent_event_keys.get(key)
        if last is not None and now - last < dedupe_seconds:
            return
        _recent_event_keys[key] = now
        if len(_recent_event_keys) > 5000:
            cutoff = now - dedupe_seconds
            for k in [k for k, t in _recent_event_keys.items() if t < cutoff]:
                del _recent_event_keys[k]
    _events.append(
        {
            "id": uuid.uuid4(),
            "kind": kind,
            "severity": severity,
            "user_id": user_id,
            "message": message[:500],
            "details": details or {},
            "ip": ip,
            "created_at": utcnow(),
        }
    )


def buffered() -> dict[str, int]:
    return {"requests": len(_requests), "ai_calls": len(_ai_calls), "events": len(_events)}


# ───────────────────────────── persistence ─────────────────────────────


def _drain(buf: deque[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    while buf:
        rows.append(buf.popleft())
    return rows


async def flush() -> int:
    """Write buffered rows to Postgres. Returns the number of rows written."""
    batches = [(RequestLog, _drain(_requests)), (AICall, _drain(_ai_calls)), (SystemEvent, _drain(_events))]
    written = 0
    async with SessionLocal() as db:
        for model, rows in batches:
            if rows:
                await db.execute(insert(model), rows)
                written += len(rows)
        await db.commit()
    return written


async def purge_old() -> str:
    cutoff = utcnow() - timedelta(days=get_settings().telemetry_retention_days)
    counts = []
    async with SessionLocal() as db:
        for model in (RequestLog, AICall, SystemEvent):
            res = await db.execute(delete(model).where(model.created_at < cutoff))
            counts.append(f"{model.__tablename__}: {getattr(res, 'rowcount', 0)}")
        await db.commit()
    return "purged " + ", ".join(counts)


# ───────────────────────────── background jobs ─────────────────────────────


async def run_job(name: str, fn: Callable[[], Awaitable[Any]]) -> None:
    st = jobs.setdefault(name, JobStatus())
    st.runs += 1
    st.last_run = utcnow()
    try:
        result = await fn()
        st.last_ok, st.last_error = True, None
        st.last_result = str(result)[:200] if result is not None else None
    except Exception as e:
        st.last_ok, st.last_error = False, f"{type(e).__name__}: {e}"[:300]
        log.exception("background job %s failed", name)
        event("job_failed", f"Background job '{name}' failed: {type(e).__name__}", severity="error")
    st.history = (st.history + [bool(st.last_ok)])[-20:]


async def every(name: str, seconds: int, fn: Callable[[], Awaitable[Any]], initial_delay: float = 0) -> None:
    jobs.setdefault(name, JobStatus()).interval_seconds = seconds
    if initial_delay:
        await asyncio.sleep(initial_delay)
    while True:
        await run_job(name, fn)
        await asyncio.sleep(seconds)


async def flush_forever() -> None:
    """Flush every 2 s. Not recorded as a job run each time (it would dominate the job table)."""
    st = jobs.setdefault("telemetry flush", JobStatus(interval_seconds=2))
    while True:
        await asyncio.sleep(2)
        try:
            n = await flush()
            st.runs += 1
            st.last_run, st.last_ok, st.last_error = utcnow(), True, None
            if n:
                st.last_result = f"wrote {n} rows"
        except Exception as e:
            st.last_ok, st.last_error = False, f"{type(e).__name__}: {e}"[:300]
            log.exception("telemetry flush failed")
