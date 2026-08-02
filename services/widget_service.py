"""
Growth OS Phase 4 -- Widget Engine.

Turns the SAME real daily signals data already behind free-signals.html,
the Telegram push, and the content-repurpose engine into two small,
embeddable widgets other websites can drop into their own pages via a
single <script> tag (services/widget_service.py computes the data;
api/widgets.py serves it + the embed JS itself).

Both widgets are honest aggregations of real technical-confluence data --
no fabricated price-change percentages, no invented "market mood." The
Sentiment Index is a confidence-weighted bull/bear ratio across today's
top signals; the "heatmap" is a signal-strength grid (direction +
confidence), not a price-change heatmap, since this codebase doesn't
compute live intraday % change for the free-signals universe.
"""
from datetime import date


def _classify_sentiment(score: int) -> str:
    if score <= 24:
        return "Extreme Fear"
    if score <= 44:
        return "Fear"
    if score <= 55:
        return "Neutral"
    if score <= 75:
        return "Greed"
    return "Extreme Greed"


def get_sentiment_index() -> dict:
    """Confidence-weighted ratio of bullish vs bearish signals in today's
    free-signals cache, mapped to a 0-100 "Fear/Greed"-style score. Falls
    back to a neutral 50 only when there's no directional data at all
    (never fabricates a score when the underlying signals are empty --
    returns available=False in that case instead)."""
    from api.market_pulse import _compute_free_signals

    cache = _compute_free_signals()
    signals = cache.get("signals") or []
    if not signals:
        return {"available": False}

    weighted_bull = 0.0
    weighted_bear = 0.0
    for s in signals:
        conf = s.get("confluence_confidence_pct")
        if conf is None:
            continue
        direction = s.get("confluence_direction")
        if direction == "偏多":
            weighted_bull += conf
        elif direction == "偏空":
            weighted_bear += conf

    total = weighted_bull + weighted_bear
    score = round((weighted_bull / total) * 100) if total else 50

    return {
        "available": True,
        "score": score,
        "label": _classify_sentiment(score),
        "date": cache.get("date") or date.today().isoformat(),
        "signals_counted": len(signals),
    }


_DIRECTION_LABEL = {"偏多": "Bullish", "偏空": "Bearish", "訊號分歧，中性": "Neutral", "數據不足": "N/A"}


def get_signal_heatmap(limit: int = 12) -> dict:
    """Top-N signals from today's cache as a compact grid: ticker, plain-
    English direction, and confidence (used as color intensity by the
    embed widget). Same real confluence data as free-signals.html --
    just reshaped for a small third-party-embeddable grid."""
    from api.market_pulse import _compute_free_signals

    cache = _compute_free_signals()
    signals = (cache.get("signals") or [])[:max(1, min(limit, 20))]
    if not signals:
        return {"available": False}

    cells = []
    for s in signals:
        raw_dir = s.get("confluence_direction")
        cells.append({
            "ticker": s.get("ticker", "?"),
            "direction": _DIRECTION_LABEL.get(raw_dir, "N/A"),
            "confidence_pct": s.get("confluence_confidence_pct"),
        })

    return {
        "available": True,
        "date": cache.get("date") or date.today().isoformat(),
        "cells": cells,
    }
