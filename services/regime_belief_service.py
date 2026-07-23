"""
Bayesian Regime Belief Service -- Stage 1 roadmap item 2 (2026-07-19):
"貝葉斯機率更新" (Bayesian probability updating).

backend/alpha/regime_detector.py classifies the CURRENT snapshot into one
hard regime label (EUPHORIA / STRONG_BULLISH / ... / PANIC) from the same
real inputs every time -- a fresh, memoryless decision on every call, with
no notion that regimes persist and evolve rather than flicker.

This module keeps a persisted probability distribution across the SAME 9
regime buckets RegimeDetector already defines, per symbol, and updates it
Bayesian-style each time new real evidence (confluence direction/
confidence, real annualized volatility, volume ratio) comes in:

    posterior(regime) ∝ prior(regime) * likelihood(evidence | regime)

The likelihood for each bucket is built from the SAME real thresholds
RegimeDetector.classify() uses (confidence >= 60, volatility >= 70/<= 30,
volume_ratio < 0.5), just expressed as smooth sigmoid "how strongly does
this evidence support this bucket" functions instead of hard if/else
cutoffs -- so a reading just under a threshold isn't treated as
categorically different from one just over it.

Before folding in the likelihood, the previous posterior is blended with
a small uniform "forgetting" term (regimes aren't permanent -- markets do
transition), the same idea as the self-transition probability in a simple
hidden Markov model, so belief adapts to genuinely new conditions instead
of ossifying after a long run of one-sided evidence.

Honesty note (same standard as the rest of this codebase): this is a
real, reproducible Bayesian update over real inputs, not a trained/
calibrated probabilistic model -- the likelihood shape is a principled
but hand-specified approximation of RegimeDetector's own rules, not
fitted to historical regime-transition data (that would need a labelled
regime-transition dataset that doesn't exist here). Every number shown is
derived from real market data; none of it is invented.
"""

import json
import math
import os
import sqlite3
from datetime import datetime, timezone
from typing import Dict, List, Optional

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "xfinlab.db")

REGIMES: List[str] = [
    "EUPHORIA", "STRONG_BULLISH", "WEAK_BULLISH", "HIGH_VOLATILITY",
    "RANGING", "LOW_LIQUIDITY", "WEAK_BEARISH", "STRONG_BEARISH", "PANIC",
]
N = len(REGIMES)
UNIFORM = 1.0 / N

# How much of the previous belief carries forward vs. resets toward
# uniform on each update -- mirrors a simple HMM's self-transition prior.
# Kept as a named constant (not tuned/fitted) so the "not a trained
# model" honesty note above stays true.
FORGETTING_FACTOR = 0.85


def _get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_table():
    conn = _get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS regime_belief (
            symbol TEXT PRIMARY KEY,
            probs_json TEXT NOT NULL,
            last_regime TEXT,
            updated_at TEXT
        )
    """)
    conn.commit()
    conn.close()


_init_table()


def _sigmoid(x: float) -> float:
    try:
        return 1.0 / (1.0 + math.exp(-x))
    except OverflowError:
        return 0.0 if x < 0 else 1.0


def _load_prior(symbol: str) -> List[float]:
    conn = _get_db()
    try:
        row = conn.execute(
            "SELECT probs_json FROM regime_belief WHERE symbol = ?", (symbol,)
        ).fetchone()
    finally:
        conn.close()
    if row:
        try:
            probs = json.loads(row["probs_json"])
            if isinstance(probs, list) and len(probs) == N:
                return probs
        except Exception:
            pass
    return [UNIFORM] * N


def _save_posterior(symbol: str, probs: List[float], top_regime: str):
    conn = _get_db()
    try:
        conn.execute(
            """INSERT INTO regime_belief (symbol, probs_json, last_regime, updated_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(symbol) DO UPDATE SET
                 probs_json=excluded.probs_json,
                 last_regime=excluded.last_regime,
                 updated_at=excluded.updated_at""",
            (symbol, json.dumps(probs), top_regime, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


def _likelihood(evidence: Dict) -> List[float]:
    """
    Smooth (sigmoid) version of RegimeDetector.classify()'s own hard
    rules -- see module docstring. `evidence` accepts the same keys as
    RegimeDetector.classify(market_data), plus an optional
    `confluence_score` (-100..100, Confluence Engine's own real weighted
    score) for a continuous bullish/bearish read instead of just the
    bucketed direction string.
    """
    score = evidence.get("confluence_score")
    if score is None:
        direction = evidence.get("trend_direction")
        score = 60 if direction == "偏多" else -60 if direction == "偏空" else 0
    volatility = evidence.get("volatility", 50) or 50
    confidence_pct = evidence.get("trend_confidence_pct", 0) or 0
    volume_ratio = evidence.get("volume_ratio")

    bullish = _sigmoid(score / 25.0)          # 0..1, 0.5 at score=0
    strong = _sigmoid((confidence_pct - 60) / 10.0)
    high_vol = _sigmoid((volatility - 70) / 8.0)
    # (a separate low_vol = _sigmoid((30 - volatility) / 8.0) signal was
    # computed here but never used -- none of the 9 REGIMES below have a
    # dedicated "low volatility" bucket; RANGING already uses (1-high_vol)
    # as its low-volatility proxy. Removed rather than left dead, but not
    # wired into the formula either -- that would be a real change to a
    # live calculation, not a lint cleanup.)
    low_liq = _sigmoid((0.5 - volume_ratio) / 0.1) if volume_ratio is not None else 0.0
    neutral_dir = max(0.0, 1 - abs(2 * bullish - 1))  # peaks at bullish=0.5

    raw = {
        "EUPHORIA": bullish * high_vol * strong,
        "STRONG_BULLISH": bullish * strong * (1 - high_vol),
        "WEAK_BULLISH": bullish * (1 - strong) * (1 - high_vol) * (1 - neutral_dir * 0.5),
        "HIGH_VOLATILITY": high_vol * (1 - strong),
        "RANGING": (1 - high_vol) * neutral_dir * (1 - low_liq),
        "LOW_LIQUIDITY": low_liq * (1 - high_vol),
        "WEAK_BEARISH": (1 - bullish) * (1 - strong) * (1 - high_vol) * (1 - neutral_dir * 0.5),
        "STRONG_BEARISH": (1 - bullish) * strong * (1 - high_vol),
        "PANIC": (1 - bullish) * high_vol * strong,
    }
    values = [max(raw[r], 1e-6) for r in REGIMES]  # floor so no bucket is ever hard-zeroed
    total = sum(values)
    return [v / total for v in values]


def update_belief(symbol: str, evidence: Dict) -> Dict:
    """
    Runs one Bayesian update for `symbol` given fresh real evidence and
    persists the new posterior. Returns:
        {"regime_probabilities": {bucket: pct, ...}, "top_regime": str,
         "top_probability_pct": float}
    """
    symbol = (symbol or "").upper().strip()
    prior = _load_prior(symbol)
    blended_prior = [FORGETTING_FACTOR * p + (1 - FORGETTING_FACTOR) * UNIFORM for p in prior]
    likelihood = _likelihood(evidence)

    unnorm = [blended_prior[i] * likelihood[i] for i in range(N)]
    total = sum(unnorm) or 1.0
    posterior = [v / total for v in unnorm]

    top_idx = max(range(N), key=lambda i: posterior[i])
    top_regime = REGIMES[top_idx]

    if symbol:
        _save_posterior(symbol, posterior, top_regime)

    return {
        "regime_probabilities": {REGIMES[i]: round(posterior[i] * 100, 1) for i in range(N)},
        "top_regime": top_regime,
        "top_probability_pct": round(posterior[top_idx] * 100, 1),
    }


def get_belief(symbol: str) -> Optional[Dict]:
    """Read-only lookup of the last-persisted belief, without updating it."""
    symbol = (symbol or "").upper().strip()
    conn = _get_db()
    try:
        row = conn.execute(
            "SELECT probs_json, last_regime, updated_at FROM regime_belief WHERE symbol = ?",
            (symbol,),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    probs = json.loads(row["probs_json"])
    return {
        "regime_probabilities": {REGIMES[i]: round(probs[i] * 100, 1) for i in range(N)},
        "top_regime": row["last_regime"],
        "updated_at": row["updated_at"],
    }
