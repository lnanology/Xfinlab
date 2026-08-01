from fastapi import APIRouter

from services.agent_debate_service import is_available, run_debate
from services.technical_analysis_service import get_technical_analysis

router = APIRouter()


@router.get("/agent-debate/status")
def agent_debate_status():
    """Frontend calls this once to decide whether to show the AI辯論
    entry point at all -- see services/agent_debate_service.py's
    docstring on why this is gated behind DEEPINFRA_API_KEY."""
    return {"available": is_available()}


@router.get("/agent-debate/{symbol}")
def agent_debate(symbol: str, token: str = None, lang: str = None):
    """
    2026-07-20 fix: this endpoint used to take no token param at all and
    never touched services/quota_middleware.py, so AI辯論 (4 sequential
    LLM calls per run -- the most expensive single feature on the site)
    rode completely outside the token-quota system anyone could hit it
    for free, repeatedly, logged in or not. Wired into the same
    check_token_budget()/record_ai_token_usage() pattern api/chat.py
    already uses: paid tiers get billed the real (summed, not
    fabricated) token cost of all 4 calls -- see
    services/agent_debate_service.py's run_debate() docstring -- against
    their existing monthly budget; free users still just earn a point
    (same as every other AI feature), never hard-blocked.
    """
    from services.quota_middleware import check_token_budget, record_ai_token_usage, require_advanced_engine_plan
    # 2026-07-26: AI辯論 (Agent Debate) is a Pro-and-above "advanced engine"
    # feature -- gated before the (expensive, 4-call) debate ever runs.
    require_advanced_engine_plan(token)
    user_id = check_token_budget(token)

    symbol = symbol.upper()
    context = {}
    try:
        tech = get_technical_analysis(symbol)
        if tech and "error" not in tech:
            context = {
                "confluence": tech.get("confluence"),
                "decision_levels": tech.get("decision_levels"),
            }
    except Exception:
        context = {}

    # Regime needs the same market_data shape as api/ai_analysis.py builds
    # -- reuse RegimeDetector directly here rather than duplicating that
    # wiring a third time; a plain volatility-only regime read is an
    # honest degraded fallback if confluence data isn't available.
    from backend.alpha.regime_detector import RegimeDetector
    confluence = context.get("confluence") or {}
    try:
        context["regime"] = RegimeDetector.classify({
            "volatility": 50,
            "trend_direction": confluence.get("direction"),
            "trend_confidence_pct": confluence.get("confidence_pct"),
        })
    except Exception:
        context["regime"] = None

    result = run_debate(symbol, context, lang=lang)
    record_ai_token_usage(user_id)
    return result
