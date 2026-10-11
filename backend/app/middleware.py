import time

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.security import CSRF_HEADER

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


class CSRFHeaderMiddleware(BaseHTTPMiddleware):
    """Every state-changing API request must carry `X-HT-Request: 1`.

    Combined with the SameSite=Lax session cookie, this blocks cross-site form posts:
    a browser won't attach a custom header to a cross-origin request without a CORS
    preflight, and CORS only allows APP_BASE_URL.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if (
            request.method not in SAFE_METHODS
            and request.url.path.startswith("/api/")
            and request.headers.get(CSRF_HEADER) != "1"
        ):
            return JSONResponse({"detail": "Missing CSRF header"}, status_code=403)
        return await call_next(request)


# Paths whose 404s mean "someone tried a share or emergency token that doesn't exist".
_TOKEN_ROUTES = ("/api/share/", "/api/emergency/")


class RequestTelemetryMiddleware:
    """Records every /api request (route template, status, latency, who) for the admin console,
    and turns denials, rate limits, server errors and bad tokens into system events.

    Pure ASGI so streaming responses (copilot SSE) pass through untouched."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope["path"].startswith("/api/") or scope["method"] == "OPTIONS":
            await self.app(scope, receive, send)
            return
        # Shared dict so `request.state.user_id` set by the auth dependency is visible here.
        state = scope.setdefault("state", {})
        started = time.monotonic()
        status_code = 500
        error: str | None = None

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception as e:
            status_code, error = 500, type(e).__name__
            raise
        finally:
            _record(scope, state, status_code, int((time.monotonic() - started) * 1000), error)


def _record(scope: Scope, state: dict, status: int, duration_ms: int, error: str | None) -> None:
    from app.services import telemetry

    route = telemetry.route_template(scope)
    user_id = state.get("user_id")
    role = state.get("role")
    method = scope["method"]
    telemetry.record_request(
        method=method, route=route, status=status, duration_ms=duration_ms, user_id=user_id, role=role, error=error
    )
    client = scope.get("client")
    ip = client[0] if client else None
    where = f"{method} {route}"
    if status >= 500:
        telemetry.event(
            "server_error",
            f"{where} failed with {status}" + (f" ({error})" if error else ""),
            severity="error",
            user_id=user_id,
            details={"route": route, "method": method, "status": status, "error": error},
            ip=ip,
        )
    elif status == 403 and route != "/api/health":
        telemetry.event(
            "access_denied",
            f"Access denied: {where}",
            severity="warning",
            user_id=user_id,
            details={"route": route, "method": method, "role": role},
            ip=ip,
            dedupe=(str(user_id or ip), route),
        )
    elif status == 429:
        telemetry.event(
            "rate_limited",
            f"Rate limit hit: {where}",
            severity="warning",
            user_id=user_id,
            details={"route": route, "method": method},
            ip=ip,
            dedupe=(str(user_id or ip), route),
            dedupe_seconds=60,
        )
    elif status == 404 and scope["path"].startswith(_TOKEN_ROUTES):
        telemetry.event(
            "invalid_token",
            f"Unknown or expired link used: {where}",
            severity="warning",
            user_id=user_id,
            details={"route": route, "method": method},
            ip=ip,
            dedupe=(str(ip), route),
            dedupe_seconds=60,
        )
