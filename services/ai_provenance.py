"""EU AI Act Article 50(2) — machine-readable marking of AI-generated content.

Context: Article 50 of the EU AI Act became enforceable on 2026-08-02. The
machine-readable marking requirement under Article 50(2) specifically got a
grace period to 2026-12-02 under the May-2026 AI Omnibus provisional
agreement, because the Commission's Code of Practice on AI-generated content
(which is meant to define the actual technical standard -- watermarking,
C2PA-style cryptographic manifests, metadata conventions, etc.) was still
being finalised. As of this writing no single technique yet satisfies all
four statutory criteria (effective/interoperable/robust/reliable)
simultaneously per the Commission's own guidance, and a "combination of
techniques ... appropriate to cost of implementation" is what the law asks
for from a provider our size.

This module is XFINLAB's good-faith implementation ahead of the Dec 2026
deadline:
  1. An HTTP response header (`X-AI-Content-Marking`) on every response from
     an API route that returns AI-generated text, applied via middleware in
     backend/main.py -- this is trivially machine-detectable by any client
     or crawler that wants to check.
  2. A small JSON provenance block (`ai_provenance()`) that the highest-value
     generative endpoint (chat.py, which returns free-form conversational AI
     text) embeds directly in its response body, so the marking travels with
     the content even if headers are stripped by an intermediary.
  3. PDF document metadata (see ai/report_generator.py) marking the AI
     Report Generator's output files.

This is NOT a claim of full C2PA/cryptographic-provenance compliance -- that
is heavier infrastructure than a solo-operator text-research platform needs
today, and the Code of Practice's final technical benchmark may ask for
more. This should be reviewed again once the Code of Practice is finalised
and before the 2026-12-02 deadline.
"""

from datetime import datetime, timezone

# Route path prefixes (matched against request.url.path, after the /api
# mount) whose responses are substantially AI-generated content -- i.e. the
# text shown to the user is produced by an LLM/statistical model, not just
# raw data passthrough. Kept as an explicit allow-list (not "everything
# under /api") so purely mechanical endpoints (auth, quota, points, push
# subscribe, watchlist CRUD, etc.) don't carry a marking header that would
# be misleading.
AI_CONTENT_ROUTE_PREFIXES = (
    "/api/chat",
    "/api/full-analysis",
    "/api/ai-analysis",
    "/api/analyze",
    "/api/screener",
    "/api/portfolio",
    "/api/anomaly",
    "/api/pairs-scan",
    "/api/research",
    "/api/report",
    "/api/news-denoise",
    "/api/compare",
    "/api/company-compare",
    "/api/stress-lab",
    "/api/chart-search",
    "/api/global-macro",
    "/api/agent-debate",
    "/api/historical-analog",
    "/api/smart-route",
    "/api/event",
    "/api/pipeline",
)

MARKING_HEADER_NAME = "X-AI-Content-Marking"
MARKING_HEADER_VALUE = "ai-generated; std=eu-ai-act-art50-good-faith"


def is_ai_content_route(path: str) -> bool:
    """True if this request path serves substantially AI-generated content."""
    return any(path.startswith(prefix) for prefix in AI_CONTENT_ROUTE_PREFIXES)


def ai_provenance(generator: str = "XFINLAB AI") -> dict:
    """Small machine-readable provenance block for embedding directly in a
    JSON response body (used where the header alone may not travel with the
    content, e.g. chat replies that get copy-pasted or logged elsewhere)."""
    return {
        "ai_generated": True,
        "generator": generator,
        "marking_standard": "eu-ai-act-art50-good-faith-v1",
        "human_review": False,
        "marked_at": datetime.now(timezone.utc).isoformat(),
    }
