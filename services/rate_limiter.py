"""2026-08-24 (site audit follow-up, "AI cost-heavy endpoints have no
tighter individual caps" -- see chat history): the shared slowapi
`Limiter` instance, extracted out of backend/main.py so per-endpoint
routers (api/ai_analysis.py, api/chat.py) can import the SAME limiter to
apply a stricter `@limiter.limit(...)` decorator on top of the blanket
100/minute default, without a circular import back to backend.main (which
imports those routers itself via include_router()).

backend/main.py still owns the actual middleware wiring (SlowAPIMiddleware,
the 429 exception handler, app.state.limiter) -- this module only owns the
Limiter object itself, matching the existing services/request_ip.py split
(get_client_ip lived there already, this just completes the same pattern
for the Limiter that uses it).
"""
from slowapi import Limiter

from services.request_ip import get_client_ip

# Blanket per-IP safety net against abuse/scraping bursts -- same default
# every endpoint already had. In-memory backend is fine for the current
# single-instance Railway deployment; would need a Redis backend if this
# ever scales to multiple instances (limits would then be per-instance,
# not global).
limiter = Limiter(key_func=get_client_ip, default_limits=["100/minute"])
