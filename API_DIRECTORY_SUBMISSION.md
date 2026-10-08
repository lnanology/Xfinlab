# XFINLAB Intelligence API — third-party directory submission copy

Ready-to-paste fields for listing the REST API (not the MCP server — see
[`MCP_MARKETPLACE_SUBMISSION.md`](MCP_MARKETPLACE_SUBMISSION.md) for that) on
APIs.guru, the Postman API Network, and RapidAPI. All three require AJ's own
account/GitHub identity on each site, so — same as the MCP submission file —
this is copy to paste in, not something that can be automated end-to-end.
Researched against each site's current (2026-08) submission docs, not
assumed from memory.

---

## Core facts (same across every listing)

| Field | Value |
|---|---|
| Name | XFINLAB Intelligence API |
| Base URL | `https://api.xfinlab.com/api/intelligence` |
| OpenAPI 3.1 spec | `https://api.xfinlab.com/api/intelligence/openapi.json` |
| Postman collection | `https://api.xfinlab.com/api/intelligence/postman.json` |
| Auth | `X-API-Key` header |
| Get a key | https://www.xfinlab.com/intelligence-api.html#access (free tier issued instantly, no approval wait) |
| Docs | https://www.xfinlab.com/intelligence-api.html |
| Category | Finance / Financial Data |
| Pricing | Free (100 weighted calls/day) / Pro $49/mo (5,000/day) / Enterprise (custom, unlimited) |

## One-liner

Real market events, FinBERT sentiment, technical/market-structure analysis, Monte Carlo stress tests, and AI-structured intelligence — every number traceable to a real computation, never fabricated.

## Short description (2-3 sentences)

XFINLAB Intelligence is a REST API for structured financial research: market events, FinBERT-scored sentiment, a 4-agent bull/bear/risk-manager debate, an AI-clustered intelligence feed, technical/market-structure analysis, historical-bootstrap stress testing, and regime-aware signal selection. Free-tier keys are issued instantly and automatically, no sales conversation required to start testing.

---

## APIs.guru submission notes

Free, no account needed — anyone can open a GitHub issue/PR against
[APIs-guru/openapi-directory](https://github.com/APIs-guru/openapi-directory),
or use their [Add API](https://apis.guru/add-api) form, pointing at a stable,
publicly reachable OpenAPI spec URL. They aggregate by URL and re-crawl it
periodically to stay in sync — no hosting or manual updates needed on our
side. Submission = the OpenAPI spec URL above.

One honest caveat before submitting: their own validator can be stricter
than FastAPI's `get_openapi()` default output (e.g. it likes a `license`
field under `info`, and a fully-resolved `servers` block, both of which our
scoped spec already has, but it's worth a manual check against their
validator, not just assuming a 200 response means it'll pass).

## Postman API Network submission notes

Requires importing our own `postman.json` collection into a Postman
workspace under AJ's account, then: Collection → Publish → enable "Allow
Collection Discovery" → "Add to API Network". Free tier account is enough;
no Enterprise plan or Community Manager approval needed for an individual
publisher. This is a natural pairing with the Postman collection endpoint
already shipped (`/api/intelligence/postman.json`) — same content, just
published through Postman's own UI instead of a bare JSON download link.

## RapidAPI submission notes

Different shape from the other two — RapidAPI acts as a **gateway**, not
just a directory: traffic is proxied through their platform, and they can
handle billing/quota enforcement on their side rather than ours. That means
listing here isn't pure discoverability like APIs.guru/Postman — it would
mean either (a) letting RapidAPI's own key/quota system sit in front of
`X-API-Key` auth (duplicate quota logic, two places pricing has to stay in
sync), or (b) more integration work to reconcile the two. Worth doing once
there's real demand to justify it, but flagged here as the one directory in
this list that isn't a "no cost, no loose ends" add — recommend treating it
as optional/lower priority relative to APIs.guru and Postman, not skipped
outright, but not a rubber-stamp submission either.
