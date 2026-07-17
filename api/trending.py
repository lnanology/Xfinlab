from fastapi import APIRouter

from services.trending_stocks_service import get_trending_for_country

router = APIRouter()


@router.get("/trending-stocks")
def trending_stocks(country: str = "US"):
    """Country-prioritized 'trending / most actively traded' stocks, used
    by js/autocomplete.js's local-first autocomplete trending section.
    `country` should be an ISO country code (e.g. HK, TW, US) -- the
    frontend passes whatever api/i18n.py's /i18n/detect resolved from the
    visitor's IP. See services/trending_stocks_service.py for the
    per-country data strategy."""
    return get_trending_for_country(country)
