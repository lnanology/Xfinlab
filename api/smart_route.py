from fastapi import APIRouter

from services.intent_router_service import route_query

router = APIRouter()


@router.get("/smart-route")
def smart_route(q: str = ""):
    """
    Powers the homepage's single "tell me what you're thinking" input
    box (js/smart-router.js): given free text, figures out which
    Engine page best answers it (and any ticker mentioned), so a
    visitor doesn't need to already know XFINLAB has 11 separate tools.

    js/smart-router.js tries its own fast regex/keyword pass first and
    only calls this endpoint when that's inconclusive -- this endpoint
    re-runs the same fast pass server-side (cheap, no harm) and falls
    back to an AI classification call only if that also comes up
    empty. See services/intent_router_service.py for the full design
    rationale.
    """
    q = (q or "").strip()
    if not q:
        return {"status": "error", "message": "請輸入你想搵嘅資產或問題"}
    return route_query(q)
