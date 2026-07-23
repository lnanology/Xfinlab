"""
Smart Beta Multi-Factor Engine -- Stage 1 roadmap items 1 + 4
(2026-07-19): "Smart Beta 多因子模型" + "動態因子切換".

Four factors, each backed by real data already available elsewhere in
this codebase -- nothing here is a fabricated/estimated number:

  Value        -- P/E ratio from services/fundamentals_service.py's real
                  SEC EDGAR data (US SEC-filing companies only; honestly
                  omitted for anything else, never guessed).
  Momentum     -- Confluence Engine's real weighted score
                  (services/technical_analysis_service.py), already
                  combining trend/RSI/MACD/support-resistance/volume/
                  SuperTrend/Ichimoku/Donchian/Keltner signals.
  Quality      -- real YoY revenue growth from the SAME SEC EDGAR annual
                  filings (see fundamentals_service.get_fundamentals's
                  `revenue_growth_pct`), gated by whether EPS is
                  currently positive. This is a growth/profitability
                  proxy, NOT a full quality model (no ROE/debt-to-equity
                  data source exists in this codebase yet) -- labelled
                  honestly as "Quality / Growth" rather than overclaiming.
  Low-Vol      -- real annualized realized volatility from actual price
                  history (services/realized_vol.py), not the
                  `volume_ratio * 15` stand-in used elsewhere.

Dynamic factor switching: rather than a fixed 25/25/25/25 blend, the
final weight on each factor is a probability-weighted average of 9
regime-specific weight presets, where the weights come from
services/regime_belief_service.py's live Bayesian regime-probability
update for this symbol (Stage 1 item 2) -- so as the market's estimated
regime shifts (e.g. more PANIC/HIGH_VOLATILITY probability mass), the
blend continuously tilts toward the Low-Vol factor without any hard
if/else regime switch.

Any factor without real supporting data for this symbol is simply
dropped from the blend (remaining weights renormalized to sum to 1)
rather than defaulted to a fabricated mid-point score.
"""

from typing import Dict, Optional

from services.fundamentals_service import get_fundamentals
from services.technical_analysis_service import get_technical_analysis, fetch_ohlc_history
from services.realized_vol import annualized_volatility_pct
from services.regime_belief_service import update_belief

# Regime -> {value, momentum, quality, low_vol} weight preset (each sums
# to 1). Hand-specified from each regime's real definition (see
# backend/alpha/regime_detector.py's docstring for what each bucket
# means), not fitted/backtested against historical regime-factor
# performance -- an honest starting point, not a claim of optimality.
REGIME_FACTOR_PRESETS: Dict[str, Dict[str, float]] = {
    "EUPHORIA":        {"value": 0.15, "momentum": 0.20, "quality": 0.15, "low_vol": 0.50},
    "STRONG_BULLISH":  {"value": 0.15, "momentum": 0.45, "quality": 0.20, "low_vol": 0.20},
    "WEAK_BULLISH":    {"value": 0.20, "momentum": 0.35, "quality": 0.25, "low_vol": 0.20},
    "HIGH_VOLATILITY": {"value": 0.20, "momentum": 0.15, "quality": 0.20, "low_vol": 0.45},
    "RANGING":         {"value": 0.40, "momentum": 0.15, "quality": 0.25, "low_vol": 0.20},
    "LOW_LIQUIDITY":   {"value": 0.20, "momentum": 0.10, "quality": 0.30, "low_vol": 0.40},
    "WEAK_BEARISH":    {"value": 0.25, "momentum": 0.15, "quality": 0.30, "low_vol": 0.30},
    "STRONG_BEARISH":  {"value": 0.20, "momentum": 0.10, "quality": 0.30, "low_vol": 0.40},
    "PANIC":           {"value": 0.10, "momentum": 0.05, "quality": 0.25, "low_vol": 0.60},
}

FACTOR_KEYS = ["value", "momentum", "quality", "low_vol"]


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _rescale(v: float, lo: float, hi: float, invert: bool = False) -> float:
    """Linearly maps v from [lo, hi] to a 0-100 score, clamped at the ends."""
    v = _clamp(v, lo, hi)
    pct = (v - lo) / (hi - lo) * 100 if hi != lo else 50.0
    return round(100 - pct, 1) if invert else round(pct, 1)


def get_smart_beta(symbol: str, current_price: Optional[float] = None) -> Dict:
    symbol = (symbol or "").upper().strip()

    tech = get_technical_analysis(symbol)
    tech_ok = bool(tech) and "error" not in tech
    confluence = tech.get("confluence", {}) if tech_ok else {}

    fundamentals = get_fundamentals(symbol, current_price=current_price or (tech.get("last_close") if tech_ok else None))

    df = fetch_ohlc_history(symbol) if tech_ok else None
    vol_pct = annualized_volatility_pct(df)

    factors: Dict[str, Dict] = {}

    # Momentum -- Confluence Engine's real -100..100 score, rescaled.
    if tech_ok and confluence:
        factors["momentum"] = {
            "score": _rescale(confluence.get("score", 0), -100, 100),
            "raw": confluence.get("score"),
            "raw_label": "Confluence score",
        }

    # Value -- real P/E, lower is "cheaper"/higher value score. Typical
    # broad-market P/E range used as the scoring band (5 = deep value,
    # 40 = richly priced); outside that range clamps to 0/100 rather
    # than extrapolating into meaningless territory.
    if fundamentals.get("available") and fundamentals.get("pe_ratio"):
        pe = fundamentals["pe_ratio"]
        factors["value"] = {
            "score": _rescale(pe, 5, 40, invert=True),
            "raw": pe,
            "raw_label": "P/E",
        }

    # Quality / Growth -- real YoY revenue growth, gated by current
    # profitability (positive EPS). -20%..+40% scoring band.
    if fundamentals.get("available") and fundamentals.get("revenue_growth_pct") is not None:
        growth = fundamentals["revenue_growth_pct"]
        eps = fundamentals.get("eps") or {}
        profitable = (eps.get("value") or 0) > 0
        score = _rescale(growth, -20, 40)
        if not profitable:
            score = min(score, 50.0)  # honest cap: unprofitable companies don't score as "high quality"
        factors["quality"] = {
            "score": score,
            "raw": growth,
            "raw_label": "Revenue YoY growth %",
            "profitable": profitable,
        }

    # Low-Volatility -- real annualized realized volatility, inverted
    # (lower vol = higher score). 10%..80% scoring band.
    if vol_pct is not None:
        factors["low_vol"] = {
            "score": _rescale(vol_pct, 10, 80, invert=True),
            "raw": vol_pct,
            "raw_label": "Annualized realized volatility %",
        }

    # ---- Dynamic factor switching: Bayesian regime-probability-weighted
    # blend of the 9 regime factor presets (Stage 1 items 2 + 4 tied
    # together). ----
    evidence = {
        "trend_direction": confluence.get("direction") if tech_ok else None,
        "confluence_score": confluence.get("score") if tech_ok else None,
        "trend_confidence_pct": confluence.get("confidence_pct") if tech_ok else 0,
        "volatility": vol_pct if vol_pct is not None else 50,
        "volume_ratio": tech.get("volume_ratio") if tech_ok else None,
    }
    regime = update_belief(symbol, evidence) if symbol else None

    dynamic_weights = {k: 0.0 for k in FACTOR_KEYS}
    if regime:
        probs = regime["regime_probabilities"]  # pct 0-100 per bucket
        for bucket, pct in probs.items():
            preset = REGIME_FACTOR_PRESETS.get(bucket)
            if not preset:
                continue
            w = pct / 100.0
            for k in FACTOR_KEYS:
                dynamic_weights[k] += w * preset[k]
    else:
        dynamic_weights = {k: 1.0 / len(FACTOR_KEYS) for k in FACTOR_KEYS}

    # Drop factors with no real data, renormalize remaining weights.
    available_keys = [k for k in FACTOR_KEYS if k in factors]
    weight_sum = sum(dynamic_weights[k] for k in available_keys) or 1.0
    used_weights = {k: round(dynamic_weights[k] / weight_sum, 3) for k in available_keys}

    blended_score = None
    if available_keys:
        blended_score = round(sum(factors[k]["score"] * used_weights[k] for k in available_keys), 1)

    return {
        "symbol": symbol,
        "factors": factors,
        "weights_used": used_weights,
        "blended_score": blended_score,
        "regime": regime,
        "data_gaps": [k for k in FACTOR_KEYS if k not in factors],
    }
