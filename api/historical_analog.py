from fastapi import APIRouter

from services.historical_analog_service import find_analogs

router = APIRouter()


@router.get("/historical-analog/{symbol}")
def historical_analog(symbol: str, forward_days: int = 10, period: str = "2y", lang: str = None):
    """Honest 'what actually happened last time this ticker was in a
    similar trend+volatility regime' read -- see services/
    historical_analog_service.py's docstring for why this replaces a
    fabricated macro-shock-slider design.

    2026-07-30 fix ("做咩又有不同語言 全網跟進"): this endpoint used to have
    no lang param at all, so every string it returned (error messages,
    regime_label, methodology sentence) was hardcoded Cantonese regardless
    of the site's selected UI language. ai-analysis.html now passes
    ?lang=<I18N.currentLang>; find_analogs() uses it to translate via
    services/i18n.py (falls back to the old Cantonese behavior when no
    lang is supplied, so any other caller is unaffected).
    """
    return find_analogs(symbol, period=period, forward_days=forward_days, lang=lang)
