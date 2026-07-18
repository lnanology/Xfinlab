"""
Shared "what is the visitor's real IP" helper.

Why this exists: this app runs on Railway, which terminates TLS and
proxies every request through its own edge before it reaches this
process -- so `request.client.host` (what slowapi's default
get_remote_address() and several endpoints were reading directly) is
Railway's internal proxy address, THE SAME for every single visitor,
not the real caller's IP. Left unfixed this quietly breaks every
IP-based feature in the app:
  - api/public_demo.py's "1 free-trial window per IP" -- with every
    visitor sharing the same apparent IP, the first visitor's trial
    window blocks everyone else's after it, not just their own.
  - backend/main.py's blanket 100/minute-per-IP rate limit (SlowAPI) --
    becomes a single 100/minute limit for the ENTIRE site's combined
    traffic instead of per real visitor.
  - backend/auth/auth.py + api/admin.py's audit-log IP recording --
    every login/register/admin action would log the same useless IP.
  - api/analytics.py's event IP field.

api/i18n.py's country-detection already read X-Forwarded-For correctly
(that endpoint's IP-based language default was working); this module
generalizes that same fix into one shared helper so every other call
site behaves the same way instead of each reinventing (or missing) it.

Trust model: Railway's own edge sets X-Forwarded-For itself for every
request that reaches this process -- a raw client can't get an
arbitrary spoofed value into it because a client can't talk to this
process directly, only through Railway's proxy. That's what makes it
safe to trust here specifically; this pattern would NOT be safe for an
app that also accepts direct, un-proxied connections.
"""
from fastapi import Request


def get_client_ip(request: Request) -> str:
    """Best-effort real client IP: X-Forwarded-For (Railway's edge sets
    this; may be a comma-separated list if there are multiple hops --
    the first entry is the original client) falling back to
    request.client.host for local/direct-connection dev use, or
    "unknown" if neither is available."""
    if request is None:
        return "unknown"
    forwarded = request.headers.get("X-Forwarded-For") or request.headers.get("x-forwarded-for")
    if forwarded:
        first = forwarded.split(",")[0].strip()
        if first:
            return first
    return request.client.host if request.client else "unknown"
