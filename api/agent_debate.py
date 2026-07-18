from fastapi import APIRouter

from services.agent_debate_service import is_available, run_debate
from services.technical_analysis_service import get_technical_analysis

router = APIRouter()


@router.get("/agent-debate/status")
def agent_debate_status():
    """Frontend calls this once to decide whether to show the AI辯論
    entry point at all -- see services/agent_debate_service.py's
    docstring on why this is gated behind DEEPSEEK_API_KEY."""
    return {"available": is_available()}


@router.get("/agent-debate/{symbol}")
def agent_debate(symbol: str):
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

    return run_debate(symbol, context)
