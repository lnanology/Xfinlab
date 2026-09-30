from fastapi import APIRouter, Request
from services.rate_limiter import limiter

router = APIRouter()


@router.post("/evidence-scorecard")
# 2026-09-29 (AJ: standalone consumer-facing page for services/
# evidence_scorecard_service.py -- separate from the Intelligence API's
# X-API-Key-gated /intelligence/v1/evidence-scorecard/{ticker}, which is
# for developers, not logged-in site users). Rate-limited like
# ai_analysis.py's endpoint -- this fans out into up to 11 real
# sub-service calls per request, the same "expensive single call" shape
# that endpoint's own comment already documents the reasoning for.
@limiter.limit("15/minute")
async def evidence_scorecard(request: Request, body: dict):
    from services.quota_middleware import is_advanced_engine_plan

    symbol = (body.get("symbol") or "").upper().strip()
    asset_class = body.get("asset_class") or "Stocks"
    token = body.get("token")

    if not symbol:
        return {"status": "ok", "data": {}}

    from services.evidence_scorecard_service import get_evidence_scorecard
    result = get_evidence_scorecard(symbol, asset_class=asset_class)

    # 2026-09-29 (AJ: "免費睇部分，鎖晒detail" -- taste-then-upgrade):
    # the AGGREGATE fields (counts, confluence_pct, has_disagreement)
    # stay visible for every plan -- that's the "taste" that shows the
    # feature is real and worth upgrading for. Only the per-dimension
    # breakdown (`dimensions`, the actual "which source said what") is
    # redacted for non-Pro, same locked-placeholder shape api/ai_analysis.py
    # already uses for Smart Beta/Scenario Lab/Regime (same
    # "advanced_engines_bundle" gate, not a new SKU).
    is_pro_plan = is_advanced_engine_plan(token, feature_key="advanced_engines_bundle")
    if not is_pro_plan:
        result["dimensions"] = None
        result["dimensions_locked"] = True
        result["required_plan"] = "pro"
        result["upgrade_url"] = "https://xfinlab.com/pricing.html"
        # 2026-09-30 (audit-trail addition): what_changed.dimension_changes
        # is the same per-dimension detail as `dimensions` above (which
        # specific source flipped, and how) -- redact it the same way for
        # non-Pro, keep the aggregate deltas (confluence_pct_delta etc.)
        # visible as part of the same "taste, not detail" contract.
        wc = result.get("what_changed")
        if isinstance(wc, dict) and "dimension_changes" in wc:
            wc["dimension_changes"] = None
            wc["dimension_changes_locked"] = True

    return {"status": "ok", "data": result}
