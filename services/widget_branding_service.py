"""
Widget Branding -- 2026-08-09, "白標套餐" (white-label package) Tier A
(XFINLAB_Final_Strategy.md P2/P3, "Enterprise white-label" follow-up).

Context: services/widget_service.py + api/widgets.py already ship a
public, unauthenticated, third-party-embeddable widget (Sentiment Index /
Signal Heatmap) -- but every render hardcodes a "Powered by XFINLAB"
badge and a fixed color palette, with zero per-client customization.
Rather than build a full bespoke "enterprise white-label instance"
speculatively for a client that doesn't exist yet (rejected this same
session -- that genuinely does need one), this closes a real, GENERIC
gap: let a PAYING client re-skin the existing widget with their own
colors/logo/co-brand or (Enterprise only) drop the XFINLAB badge
entirely. This doesn't require knowing anything about a specific
client's business -- it's the same feature regardless of who buys it,
so it's safe to build ahead of a signed deal.

Tiering (mirrors services/intelligence_quota_service.py's TIER_LIMITS
tier strings so this reuses the SAME tier column already on api_keys /
self_serve_api_keys, no new tier taxonomy invented):
  - free / no key at all -> branding unavailable, embed.js silently
    keeps today's default XFINLAB-branded rendering (zero regression
    for the ~0 clients using this today).
  - pro                  -> accent_color + logo_url + "cobrand" badge
                             ("Powered by XFINLAB × {brand_name}") --
                             still carries XFINLAB attribution/backlink,
                             just co-branded.
  - enterprise            -> everything Pro gets, PLUS badge_mode="hidden"
                             (badge fully removed) -- reserved for the
                             highest tier specifically because giving up
                             the XFINLAB backlink/attribution entirely is
                             the strongest ask, and Enterprise is already
                             the "talk to us" tier in pricing.html where
                             that tradeoff gets negotiated explicitly.

Honesty/safety contract: set_branding() always re-verifies the caller's
key and its CURRENT tier via api_key_service.verify_key() at write time
-- a client whose key gets downgraded/revoked can't keep an old
badge_mode="hidden" row lingering past their entitlement, since
get_branding_for_embed() ALSO re-checks tier at read time (every embed
load), not just at config-write time.
"""

import os
import re
import sqlite3
from datetime import datetime, timezone
from typing import Dict, Optional

from services.api_key_service import verify_key

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "xfinlab.db")

_HEX_COLOR_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}){1,2}$")
_BADGE_MODES = {"default", "cobrand", "hidden"}
_MAX_BRAND_NAME_LEN = 40


def _get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_table():
    conn = _get_db()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS widget_branding (
            api_key TEXT PRIMARY KEY,
            brand_name TEXT,
            accent_color TEXT,
            logo_url TEXT,
            badge_mode TEXT DEFAULT 'default',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT
        )
        """
    )
    conn.commit()
    conn.close()


_init_table()


def _validate(brand_name: Optional[str], accent_color: Optional[str], logo_url: Optional[str], badge_mode: str) -> Optional[str]:
    if badge_mode not in _BADGE_MODES:
        return f"badge_mode must be one of {sorted(_BADGE_MODES)}"
    if brand_name and len(brand_name) > _MAX_BRAND_NAME_LEN:
        return f"brand_name too long (max {_MAX_BRAND_NAME_LEN} chars)"
    if accent_color and not _HEX_COLOR_RE.match(accent_color):
        return "accent_color must be a hex color, e.g. #2563eb"
    if logo_url and not logo_url.startswith("https://"):
        return "logo_url must be an https:// URL"
    if badge_mode == "cobrand" and not brand_name:
        return "badge_mode='cobrand' requires brand_name"
    return None


def set_branding(
    api_key: str,
    brand_name: Optional[str] = None,
    accent_color: Optional[str] = None,
    logo_url: Optional[str] = None,
    badge_mode: str = "default",
) -> Dict:
    """Admin-only setter (called from api/admin.py, itself gated by
    verify_admin -- this function has no auth of its own, same convention
    as other admin-invoked service functions in this codebase).

    Returns {"success": True} or {"success": False, "message": "..."}.
    Re-verifies the key's tier at write time so an Enterprise-only
    badge_mode="hidden" can never be set on a key that isn't actually
    Enterprise, even if the admin fat-fingers it."""
    auth = verify_key(api_key)
    if not auth["valid"]:
        return {"success": False, "message": "Unknown or inactive API key."}

    tier = auth["tier"]
    if tier not in ("pro", "enterprise"):
        return {"success": False, "message": f"Widget branding requires Pro or Enterprise tier (this key is '{tier}')."}
    if badge_mode == "hidden" and tier != "enterprise":
        return {"success": False, "message": "badge_mode='hidden' (fully remove the XFINLAB badge) requires Enterprise tier."}

    error = _validate(brand_name, accent_color, logo_url, badge_mode)
    if error:
        return {"success": False, "message": error}

    conn = _get_db()
    try:
        conn.execute(
            """
            INSERT INTO widget_branding (api_key, brand_name, accent_color, logo_url, badge_mode, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(api_key) DO UPDATE SET
                brand_name=excluded.brand_name,
                accent_color=excluded.accent_color,
                logo_url=excluded.logo_url,
                badge_mode=excluded.badge_mode,
                updated_at=excluded.updated_at
            """,
            (api_key, brand_name, accent_color, logo_url, badge_mode, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        return {"success": True}
    finally:
        conn.close()


def get_branding_for_embed(api_key: Optional[str]) -> Dict:
    """Public read path -- called by GET /widgets/branding, which
    embed.js fetches when a data-xfl-key attribute is present. NEVER
    raises; any failure/missing-key/downgraded-tier case returns
    {"available": False} so embed.js's caller-side fallback is simply
    "render today's default XFINLAB branding", never a broken widget.

    Re-checks tier at READ time (not just at set_branding() write time)
    -- a downgraded/revoked key stops getting its custom branding on the
    very next embed load, not whenever an admin happens to clean up the
    row."""
    if not api_key:
        return {"available": False}

    auth = verify_key(api_key)
    if not auth["valid"] or auth["tier"] not in ("pro", "enterprise"):
        return {"available": False}

    conn = _get_db()
    try:
        row = conn.execute("SELECT * FROM widget_branding WHERE api_key=?", (api_key,)).fetchone()
    finally:
        conn.close()

    if not row:
        return {"available": False}

    badge_mode = row["badge_mode"] or "default"
    if badge_mode == "hidden" and auth["tier"] != "enterprise":
        # Tier was downgraded after "hidden" was set -- honest re-check,
        # never keep honoring an entitlement the key no longer has.
        badge_mode = "cobrand" if row["brand_name"] else "default"

    return {
        "available": True,
        "tier": auth["tier"],
        "brand_name": row["brand_name"],
        "accent_color": row["accent_color"],
        "logo_url": row["logo_url"],
        "badge_mode": badge_mode,
    }
