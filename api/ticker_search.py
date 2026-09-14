import logging

from fastapi import APIRouter

from services.ticker_search_service import search_global_assets

router = APIRouter()
logger = logging.getLogger(__name__)

# 2026-09-14 hardening (site-wide pain-points audit finding #2 -- "backend
# error handling"): `q` used to go straight into search_global_assets()
# with no length cap and no try/except -- an autocomplete box lets a user
# type arbitrarily long text, and any exception from the underlying Yahoo
# Finance search call (network hiccup, unexpected response shape) fell
# through as a raw 500 with no JSON body js/autocomplete.js could parse.
# 64 chars is generously above any real ticker/company-name query length.
_MAX_QUERY_LEN = 64


@router.get("/ticker-search")
def ticker_search(q: str = ""):
    """Live global asset search, used by js/autocomplete.js to
    supplement its local curated ~230-ticker list with real matches
    from Yahoo Finance's search index -- so any valid ticker (not just
    the ones hand-picked into ASSETS) shows up as a suggestion."""
    q = (q or "").strip()[:_MAX_QUERY_LEN]
    try:
        results = search_global_assets(q)
    except Exception:
        logger.exception("ticker_search: search_global_assets failed for query %r", q)
        results = []
    return {"query": q, "results": results}
