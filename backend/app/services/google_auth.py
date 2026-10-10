"""Google ID-token verification (Sign in with Google, ID-token flow)."""

from typing import Any

from fastapi.concurrency import run_in_threadpool
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from app.config import get_settings


class GoogleAuthError(Exception):
    pass


_transport = google_requests.Request()


def _verify_sync(credential: str, client_id: str) -> dict[str, Any]:
    return id_token.verify_oauth2_token(credential, _transport, client_id)


async def verify_google_token(credential: str) -> dict[str, Any]:
    """Verify signature, expiry, issuer and audience; return the claims.

    Raises GoogleAuthError if the token is invalid or the email is not verified.
    """
    client_id = get_settings().google_client_id
    if not client_id:
        raise GoogleAuthError("Google sign-in is not configured on this server")
    try:
        # Fetches Google's public certs over HTTP (cached), so run off the event loop.
        claims = await run_in_threadpool(_verify_sync, credential, client_id)
    except ValueError as e:  # wrong audience, expired, bad signature, ...
        raise GoogleAuthError("Invalid Google credential") from e
    if claims.get("aud") != client_id:
        raise GoogleAuthError("Token audience mismatch")
    if not claims.get("email_verified"):
        raise GoogleAuthError("Google email is not verified")
    return claims
