from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

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
