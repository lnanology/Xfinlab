"""2026-08-28 (AJ, "0成本推廣" -> viral share loop): lets any visitor on
ai-analysis.html download a branded 1200x630 PNG "research card" for
whatever ticker they just analyzed, to share on Telegram/X/WhatsApp --
each shared image carries the XFINLAB wordmark, so every share is free
brand distribution back to whoever sees it.

Deliberately reuses services/telegram_push_service.py's
generate_research_card() -- the exact same Pillow renderer already proven
in production for the daily Telegram auto-post (see backend/main.py's
_notify_free_signals_ready job) -- rather than a second image-rendering
implementation. That function was written generically (`sig: dict`, not
hardcoded to the daily scan-cache pick), so this endpoint is the second,
on-demand caller it was designed to support.

Deliberately does NOT trust ticker stats from the client (no
direction/confidence query params) -- recomputes
technical_analysis_service.get_technical_analysis() server-side from the
ticker alone. Two reasons: (1) matches this codebase's "never a separate,
possibly-drifting computation" convention -- the shared card should show
XFINLAB's own number, not whatever a client claims it is, and (2) a
client-trusted confidence/direction would let anyone forge a fake-bullish
"XFINLAB says BUY" card for a pump, which a real recomputation prevents.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request, Response

from services.rate_limiter import limiter

router = APIRouter()

_CARD_LANGS = {"en", "zh", "es"}


@router.get("/research-card/{ticker}")
@limiter.limit("10/minute")
def research_card(request: Request, ticker: str, lang: str = "en"):
    from services.technical_analysis_service import get_technical_analysis
    from services.telegram_push_service import generate_research_card

    ticker = ticker.upper().strip()
    if not ticker:
        raise HTTPException(status_code=422, detail="ticker is required")

    tech = get_technical_analysis(ticker, period="6mo", interval="1d", lang="en")
    if not tech or "error" in tech:
        raise HTTPException(status_code=404, detail=(tech or {}).get("error", f"No data available for {ticker}"))

    confluence = tech.get("confluence") or {}
    sig = {
        "ticker": tech.get("symbol", ticker),
        "label": ticker,
        "confluence_direction": confluence.get("direction"),
        "confluence_confidence_pct": confluence.get("confidence_pct"),
    }
    card_lang = lang if lang in _CARD_LANGS else "en"
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    png_bytes = generate_research_card(sig, card_lang, date_str)
    if not png_bytes:
        raise HTTPException(status_code=503, detail="Card generation temporarily unavailable")

    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={"Content-Disposition": f'inline; filename="XFINLAB-{ticker}-research-card.png"'},
    )
