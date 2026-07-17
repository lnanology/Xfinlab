from fastapi import APIRouter

from services.ticker_search_service import search_global_assets

router = APIRouter()


@router.get("/ticker-search")
def ticker_search(q: str = ""):
    """Live global asset search, used by js/autocomplete.js to
    supplement its local curated ~230-ticker list with real matches
    from Yahoo Finance's search index -- so any valid ticker (not just
    the ones hand-picked into ASSETS) shows up as a suggestion."""
    return {"query": q, "results": search_global_assets(q)}
