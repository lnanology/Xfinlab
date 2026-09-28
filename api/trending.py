from fastapi import APIRouter

from services.trending_stocks_service import (
    ALLOWED_DAYS, ASSET_CLASSES, DEFAULT_DAYS, SECTORS, get_trending_for_country,
)

router = APIRouter()


@router.get("/trending-stocks")
def trending_stocks(country: str = "US", sector: str = None, days: int = DEFAULT_DAYS, asset_class: str = None):
    """Country-prioritized 'trending / most actively traded' stocks, used
    by js/autocomplete.js's local-first autocomplete trending section
    (which only ever passes `country`) and by admin.html's "Most Active
    Stocks" lookup (which also uses `sector`/`days`/`asset_class`).

    `country` should be an ISO country code (e.g. HK, TW, US) -- the
    frontend passes whatever api/i18n.py's /i18n/detect resolved from the
    visitor's IP. Ignored when `asset_class` is given and isn't "Stocks".

    `sector` (optional, 2026-09-28): one of SECTORS -- see
    /trending-stocks/sectors. Case-insensitive. Only the US basket has
    full 5-tickers-per-sector coverage; other countries just tag their
    existing small basket, so a sector filter there may return very few
    (or zero) results, which is an honest reflection of how small those
    curated baskets are. Ignored when `asset_class` isn't "Stocks".

    `days` (optional, 2026-09-28): trailing trading-session window for
    the volume ranking -- one of ALLOWED_DAYS. Any other value is
    silently snapped to DEFAULT_DAYS. See
    services/trending_stocks_service.py for the per-country data
    strategy and why this needed real fixing (not just a new parameter)
    to be accurate.

    `asset_class` (optional, 2026-09-28): one of ASSET_CLASSES -- see
    /trending-stocks/sectors. Defaults to "Stocks" (the country/sector
    basket above). Futures/Commodities/Forex/Crypto/Indices each rank a
    fixed small basket of real, liquid US-listed instruments -- see
    ASSET_CLASS_BASKETS in trending_stocks_service.py for exactly which
    tickers and why each class uses the ticker format (ETF proxy vs. raw
    futures/forex/crypto symbol) it does."""
    return get_trending_for_country(country, sector=sector, days=days, asset_class=asset_class)


@router.get("/trending-stocks/sectors")
def trending_stocks_sectors():
    """The fixed sector list `sector` accepts, the asset classes
    `asset_class` accepts, and the day windows `days` accepts -- lets a
    frontend build its filter dropdowns without hardcoding any of the
    three twice."""
    return {
        "sectors": SECTORS, "asset_classes": ASSET_CLASSES,
        "allowed_days": list(ALLOWED_DAYS), "default_days": DEFAULT_DAYS,
    }
