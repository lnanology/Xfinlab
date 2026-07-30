"""
News Impact Engine -- Phase 2 of the AI Intelligence Engine (2026-07-31).

Phase 1 (services/ai_news_object_service.py, commit dfaf965) deliberately
left impact_score/confidence/probability/risk_level/time_horizon as None
with quant_pending=True rather than asking an LLM to invent plausible-
looking numbers. This module fills those fields honestly by calling
REAL, already-built quant engines per affected_assets ticker:

  1. services/market_data_gateway.get_ohlc(ticker)
       -> real OHLC history (Alpaca/yfinance, whichever is wired live).
  2. services/market_structure_engine.compute_market_structure(df)
       -> a real technical read of the CURRENT trend/volatility/
          structural-confidence context this ticker is in right now.
          This is NOT a prediction about the news event itself -- it's
          an honest description of the market structure the news lands
          in, same "weights_calibrated: False" disclosed-heuristic
          posture that module already holds itself to.
  3. services/historical_analog_service.find_analogs(ticker)
       -> a real backtested statistic: historically, when this ticker
          was in a similar (trend + volatility) regime to today, what %
          of the time did it rise over the next N days, and by how much.
          Also NOT a prediction -- a retrospective frequency count.

None of these three engines know anything about the specific news event
-- they describe the ticker's current/historical technical context. That
is an intentional, disclosed limitation (documented in each field's
"_methodology" string below), not a bug: measuring the ACTUAL causal
market impact of one specific news item would need an event-study design
(comparing realized returns immediately around this exact publish
timestamp against a random-day baseline) that doesn't exist in this
codebase yet -- a candidate for a future Phase, not invented here.

Honesty contract (same standard as every other engine in this codebase):
  - Every ticker is looked up independently; a fetch failure or
    insufficient-data response for one ticker is recorded under that
    ticker's own `error` key and excluded from the aggregate -- never
    silently defaulted or averaged-in as zero.
  - If EVERY ticker fails (or affected_assets is empty), the Phase-1
    placeholders are left completely untouched: quant_pending stays
    True, impact_score/confidence/probability/risk_level/time_horizon
    stay None. Never "confidence: 50" as a fake neutral fallback.
  - `quant_signals.per_asset` is kept on the returned object so every
    aggregate number is traceable back to exactly which ticker and
    engine produced it -- the same traceability discipline
    ai_news_object_service.py's `citations` list already applies to
    headline sourcing.

`event_chain` (the Knowledge Graph concept from the user's proposal)
remains explicitly out of scope here -- deferred to a later phase per
the original 5-phase plan, since it needs its own backtested
correlation-chain infrastructure (reusing services/backtest_service.py),
not something this per-ticker enrichment can honestly produce as a
side effect.
"""

import logging
from statistics import mean
from typing import Dict, List, Optional

from services.market_data_gateway import get_ohlc
from services.market_structure_engine import compute_market_structure
from services.historical_analog_service import find_analogs

logger = logging.getLogger(__name__)

# Bounds latency/cost of one enrichment call -- most news_object clusters
# tag 1-2 tickers anyway (see ai_news_object_service._extract_entities's
# ~25-entry known-entity list); this just guards against a pathological
# cluster tagging many tickers at once (e.g. a broad "Fed" headline that
# happens to also cashtag several names).
_DEFAULT_MAX_ASSETS = 3

# Heuristic scaling factor turning an average |forward return %| into a
# 0-100 "impact_score" -- NOT backtested/calibrated (same documented gap
# as ai_news_object_service.py's _importance_score). A 5% average
# historical forward move under this regime maps to 100 (saturates);
# smaller historical moves scale down linearly. Revisit this constant if
# real outcome data ever lets it be calibrated properly.
_IMPACT_SCALE = 20


def _classify_risk(avg_volatility_score: Optional[float]) -> Optional[str]:
    """Maps market_structure_engine's real 0-100 volatility_score (already
    an ATR-based, disclosed-heuristic composite -- see that module) into
    a 3-bucket risk_level label. None in, None out -- never guessed."""
    if avg_volatility_score is None:
        return None
    if avg_volatility_score >= 70:
        return "high"
    if avg_volatility_score >= 40:
        return "medium"
    return "low"


def _classify_time_horizon(forward_days: Optional[int]) -> Optional[str]:
    """Maps historical_analog_service's real `forward_days` window (the
    N-day-ahead window its win_rate_pct/avg_forward_return_pct are
    actually measured over) into a human label -- traceable to the exact
    window used, not an independent guess."""
    if forward_days is None:
        return None
    if forward_days <= 5:
        return "short_term"
    if forward_days <= 20:
        return "medium_term"
    return "long_term"


def _enrich_one_asset(ticker: str) -> Dict:
    """Real per-ticker lookup. Never raises -- any failure is captured in
    the returned dict's `error` key so the caller can exclude it from
    aggregates without the whole enrichment call failing."""
    entry: Dict = {"ticker": ticker}

    try:
        df = get_ohlc(ticker, period="1y", interval="1d")
    except Exception as e:
        entry["error"] = f"OHLC 數據攞唔到（{ticker}）：{e}"
        return entry

    if df is None or df.empty:
        entry["error"] = f"OHLC 數據為空（{ticker}）"
        return entry

    structure = compute_market_structure(df)
    if structure is None:
        entry["structure_error"] = f"市場結構數據不足（{ticker}），未能計算 trend/confidence/volatility"
    else:
        entry["trend_score"] = structure["trend_score"]
        entry["confidence"] = structure["confidence"]
        entry["volatility_score"] = structure["volatility_score"]
        entry["prior_structure"] = structure["prior_structure"]

    try:
        analog = find_analogs(ticker)
    except Exception as e:
        entry["analog_error"] = f"歷史類比計算失敗（{ticker}）：{e}"
        return entry

    if analog.get("error"):
        entry["analog_error"] = analog["error"]
    elif not analog.get("match_count"):
        entry["analog_note"] = analog.get("note", f"{ticker} 無足夠歷史類比樣本")
    else:
        entry["win_rate_pct"] = analog["win_rate_pct"]
        entry["avg_forward_return_pct"] = analog["avg_forward_return_pct"]
        entry["regime_label"] = analog["regime_label"]
        entry["forward_days"] = analog["forward_days"]
        entry["match_count"] = analog["match_count"]

    return entry


def enrich_with_quant_signals(news_object: Dict, max_assets: int = _DEFAULT_MAX_ASSETS) -> Dict:
    """
    Mutates and returns `news_object` (a dict built by
    ai_news_object_service.build_news_object()), filling in
    impact_score/confidence/probability/risk_level/time_horizon from real
    per-ticker computations over its `affected_assets` list.

    Leaves the object completely untouched (quant_pending stays True) if:
      - affected_assets is empty (nothing to look up), or
      - every ticker lookup failed / returned insufficient data.

    On partial success (some tickers resolved, others didn't), aggregates
    only over the tickers that DID resolve, and records every ticker's
    individual result (including failures) under `quant_signals.per_asset`
    for traceability. `quant_pending` flips to False as soon as at least
    one ticker contributes real confidence or probability data.
    """
    tickers = (news_object.get("affected_assets") or [])[:max_assets]
    if not tickers:
        news_object.setdefault("quant_signals", {
            "per_asset": {},
            "note": "冇 affected_assets 可以查詢，Phase 2 量化欄位維持 pending。",
        })
        return news_object

    per_asset: Dict[str, Dict] = {}
    for ticker in tickers:
        per_asset[ticker] = _enrich_one_asset(ticker)

    confidences = [e["confidence"] for e in per_asset.values() if "confidence" in e]
    volatilities = [e["volatility_score"] for e in per_asset.values() if "volatility_score" in e]
    win_rates = [e["win_rate_pct"] for e in per_asset.values() if "win_rate_pct" in e]
    fwd_returns = [e["avg_forward_return_pct"] for e in per_asset.values() if "avg_forward_return_pct" in e]
    forward_days_list = [e["forward_days"] for e in per_asset.values() if "forward_days" in e]

    if not confidences and not win_rates:
        news_object["quant_signals"] = {
            "per_asset": per_asset,
            "note": "所有資產都攞唔到足夠數據（OHLC/市場結構/歷史類比），Phase 2 量化欄位維持 pending。",
        }
        return news_object

    avg_confidence = round(mean(confidences), 1) if confidences else None
    avg_volatility = round(mean(volatilities), 1) if volatilities else None
    avg_win_rate = round(mean(win_rates), 1) if win_rates else None
    avg_magnitude = round(mean(abs(r) for r in fwd_returns), 2) if fwd_returns else None
    dominant_forward_days = forward_days_list[0] if forward_days_list else None

    news_object["confidence"] = avg_confidence
    news_object["probability"] = avg_win_rate
    news_object["impact_score"] = (
        round(min(avg_magnitude * _IMPACT_SCALE, 100), 1) if avg_magnitude is not None else None
    )
    news_object["risk_level"] = _classify_risk(avg_volatility)
    news_object["time_horizon"] = _classify_time_horizon(dominant_forward_days)
    news_object["quant_pending"] = False

    news_object["quant_signals"] = {
        "per_asset": per_asset,
        "assets_used": [t for t in tickers if "confidence" in per_asset.get(t, {}) or "win_rate_pct" in per_asset.get(t, {})],
        "methodology": (
            "confidence/risk_level 嚟自 market_structure_engine 對每隻資產「現時」技術結構"
            "（趨勢/波動）嘅真實計算；probability/impact_score/time_horizon 嚟自 "
            "historical_analog_service 對呢隻資產喺相似（趨勢＋波動）組合下嘅真實歷史回測統計。"
            "呢啲數字描述緊資產本身嘅現時／歷史技術面，並非對呢單新聞事件本身未來影響嘅預測，"
            "亦非投資建議。"
        ),
    }
    return news_object


if __name__ == "__main__":
    import json

    # Smoke test using a ticker that (per this module's own honesty
    # contract) may legitimately fail in network-restricted environments
    # -- the point of this test is to confirm graceful degradation
    # (error captured per-asset, quant_pending left True) works, not to
    # prove a live network call succeeds.
    sample_object = {
        "id": "news_test",
        "affected_assets": ["AAPL"],
        "quant_pending": True,
        "impact_score": None,
        "confidence": None,
        "probability": None,
        "risk_level": None,
        "time_horizon": None,
    }
    result = enrich_with_quant_signals(sample_object)
    print(json.dumps(result, indent=2, ensure_ascii=False))
