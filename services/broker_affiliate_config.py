"""2026-07-31 (monetization batch, task #599): broker-referral CTA config.

IMPORTANT -- read before touching this file: every `affiliate_url` below is
deliberately `None`. XFINLAB has NOT signed up for any broker affiliate
program yet, so there is no real tracking link to put here. Fabricating a
plausible-looking affiliate URL (or pointing at a broker's plain homepage
and calling it an "affiliate link") would misrepresent a partnership that
doesn't exist and would earn zero commission anyway -- worse, it would
silently ship a broken monetization feature that looks like it's working.

How to actually turn this on:
  1. Apply to the broker's real affiliate/partner program (e.g. Interactive
     Brokers' "Referral Program", Webull's affiliate program, etc.).
  2. Once approved, paste your real tracking URL into that broker's
     `affiliate_url` field below.
  3. get_active_brokers() below only returns brokers with a non-empty
     affiliate_url -- so the CTA (api/broker_affiliates.py ->
     js/broker-cta.js) silently renders NOTHING on the live site until at
     least one entry here is filled in. Nothing fake ever reaches a user.

Deliberately NOT tied to any specific BUY/SELL signal or ticker -- same
"no trading signals" posture as the rest of this codebase's Paddle-
compliance work (tasks #518-523: BUY/SELL wording softened, Entry/Stop/TP
rewritten as descriptive levels). This CTA is a neutral "here are brokers
if you want to act on your own research" panel, never "this analysis says
buy, so open an account here".
"""
from typing import Dict, List, Optional

# Each entry: id, display name, one-line neutral description (no
# performance/return claims -- most affiliate program terms actually
# prohibit that kind of copy anyway), region tags for optional future
# geo-targeting, and affiliate_url (fill in once approved).
BROKERS: List[Dict] = [
    {
        "id": "ibkr",
        "name": "Interactive Brokers",
        "description": "Global broker covering stocks, options, futures, forex, and bonds across 150+ markets.",
        "regions": ["global", "us", "hk", "eu"],
        "affiliate_url": None,
    },
    {
        "id": "moomoo",
        "name": "Moomoo",
        "description": "US/HK/SG broker with commission-free US stock trading and built-in charting tools.",
        "regions": ["us", "hk", "sg"],
        "affiliate_url": None,
    },
    {
        "id": "webull",
        "name": "Webull",
        "description": "US broker offering commission-free stock, ETF, and options trading.",
        "regions": ["us"],
        "affiliate_url": None,
    },
    {
        "id": "tiger_brokers",
        "name": "Tiger Brokers",
        "description": "Asia-focused broker covering US, HK, SG, and China A-share markets.",
        "regions": ["hk", "sg", "cn"],
        "affiliate_url": None,
    },
]


def get_active_brokers(region: Optional[str] = None) -> List[Dict]:
    """Returns only brokers with a real affiliate_url configured -- see
    module docstring. `region` optionally filters further (e.g. "hk"), but
    a broker missing its affiliate_url is excluded regardless of region."""
    active = [b for b in BROKERS if b.get("affiliate_url")]
    if region:
        active = [b for b in active if region in b.get("regions", [])]
    return [
        {"id": b["id"], "name": b["name"], "description": b["description"], "url": b["affiliate_url"]}
        for b in active
    ]
