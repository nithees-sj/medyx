from slowapi import Limiter
from slowapi.util import get_remote_address

# Applied per-route to auth, emergency, share-claim and AI endpoints.
limiter = Limiter(key_func=get_remote_address)

AUTH_LIMIT = "20/minute"
EMERGENCY_LIMIT = "30/minute"
CLAIM_LIMIT = "10/minute"
AI_LIMIT = "30/minute"
