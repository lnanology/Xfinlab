"""
Formula Composer Service -- P2 of the Quant Research Factory roadmap
(2026-08-10), small-scale combinatorial strategy generator.

What this actually does, stated plainly up front: it does NOT touch the
82-formula FORMULA_CATALOG in services/formula_catalog.py (those are
generic math formulas -- Black-Scholes, Sharpe ratio, bond duration,
SymPy solvers -- with no shared boolean-signal interface, so "combining"
them pairwise has no well-defined meaning for a trading rule). Instead it
composes the SAME six atomic long/short primitives that services/
backtest_service.py's confluence_trend strategy already blends together
internally (trend-vs-SMA50, RSI extreme, MACD histogram sign, Bollinger
band touch, OBV trend, 20-bar Donchian breakout) into NEW candidate rules
via simple boolean logic -- pairwise AND (both must agree) and
triple-wise 2-of-3 majority vote -- then validates every candidate
through services/backtest_service.py's real walk-forward/OOS machinery
(BacktestService._walk_forward_core(), added in this same roadmap's P0
step) before keeping anything.

This is deliberately "small-scale": 6 primitives -> C(6,2)=15 pairs +
C(6,3)=20 triples = 35 candidates per symbol, not a genetic-algorithm/
exhaustive search over thousands of parameter combinations. A brute-force
search over a much larger space would just be a more efficient way to
overfit a specific historical period -- see the module docstring on
backtest_service.py's run_walk_forward() for why P0 (real transaction
costs + walk-forward validation) had to exist before ANY composition step
could produce something more trustworthy than noise. Every candidate here
is filtered through the exact same overfitting-risk heuristic and a
minimum-out-of-sample-trade-count floor before it is even eligible to be
called a "result", and every response still carries the same honesty
caveats as the rest of this codebase's backtest surface.

Why reuse the primitives instead of composing new indicators: every one
of these six primitives is already a battle-tested, look-ahead-free
signal (see backtest_service.py's _compute_causal_indicators() and its
_signal_confluence_trend() implementation, which this module intentionally
mirrors at the atomic level) -- introducing brand-new indicator math here
would reopen exactly the look-ahead-bias risk backtest_service.py's own
module docstring goes out of its way to document and avoid.

Persistence: results are cached per (symbol, label) in a small sqlite
table (same DB_PATH/pattern as services/prediction_ledger_service.py),
upserted on every scan so re-scanning a symbol refreshes its leaderboard
row rather than accumulating duplicate history -- this is a leaderboard
of "best composite found so far per symbol", not an audit log; nothing
here is a live trading signal.
"""

import itertools
import logging
import os
import sqlite3
from datetime import datetime, timezone
from typing import Dict, List, Optional

import numpy as np

from services.backtest_service import (
    DEFAULT_COMMISSION_PCT,
    DEFAULT_SLIPPAGE_PCT,
    WARMUP_BARS,
    BacktestService,
)
from services.technical_analysis_service import TechnicalAnalysisService

logger = logging.getLogger(__name__)

_svc = TechnicalAnalysisService

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "xfinlab.db")

# ---- the six atomic primitives, each (i, ind) -> "long" | "short" | None,
# reading only ind[...][i] (already-computed causal series from
# BacktestService._compute_causal_indicators) -- see module docstring. ----


def _prim_trend_sma50(i: int, ind: Dict) -> Optional[str]:
    t = ind["trend"][i]
    if t == 1:
        return "long"
    if t == -1:
        return "short"
    return None


def _prim_rsi_extreme(i: int, ind: Dict) -> Optional[str]:
    rsi = ind["rsi"][i]
    if rsi is None or np.isnan(rsi):
        return None
    if rsi <= 30:
        return "long"
    if rsi >= 70:
        return "short"
    return None


def _prim_macd_sign(i: int, ind: Dict) -> Optional[str]:
    h = ind["macd_hist"][i]
    if h is None or np.isnan(h):
        return None
    return "long" if h > 0 else "short"


def _prim_bollinger_touch(i: int, ind: Dict) -> Optional[str]:
    close = ind["close"][i]
    bb_upper, bb_lower = ind["bb_upper"][i], ind["bb_lower"][i]
    if bb_upper is None or np.isnan(bb_upper):
        return None
    if close <= bb_lower:
        return "long"
    if close >= bb_upper:
        return "short"
    return None


def _prim_obv_trend(i: int, ind: Dict) -> Optional[str]:
    t = ind["obv_trend"][i]
    if t == 1:
        return "long"
    if t == -1:
        return "short"
    return None


def _prim_donchian20_breakout(i: int, ind: Dict) -> Optional[str]:
    close = ind["close"][i]
    dh, dl = ind["donchian_high"][i], ind["donchian_low"][i]
    if dh is None or np.isnan(dh) or dl is None or np.isnan(dl):
        return None
    if close > dh:
        return "long"
    if close < dl:
        return "short"
    return None


PRIMITIVES = {
    "trend_sma50": _prim_trend_sma50,
    "rsi_extreme": _prim_rsi_extreme,
    "macd_sign": _prim_macd_sign,
    "bollinger_touch": _prim_bollinger_touch,
    "obv_trend": _prim_obv_trend,
    "donchian20_breakout": _prim_donchian20_breakout,
}

# ---- combinatorial candidate generation ----


def _make_and_signal(name_a: str, name_b: str):
    fn_a, fn_b = PRIMITIVES[name_a], PRIMITIVES[name_b]

    def _signal(i: int, ind: Dict) -> Optional[str]:
        va, vb = fn_a(i, ind), fn_b(i, ind)
        if va is not None and va == vb:
            return va
        return None

    return _signal


def _make_vote_signal(name_a: str, name_b: str, name_c: str):
    fn_a, fn_b, fn_c = PRIMITIVES[name_a], PRIMITIVES[name_b], PRIMITIVES[name_c]

    def _signal(i: int, ind: Dict) -> Optional[str]:
        votes = [v for v in (fn_a(i, ind), fn_b(i, ind), fn_c(i, ind)) if v is not None]
        if votes.count("long") >= 2:
            return "long"
        if votes.count("short") >= 2:
            return "short"
        return None

    return _signal


def generate_candidates() -> List[Dict]:
    """Returns [{"label", "logic", "primitives": [...], "signal_fn"}, ...]
    -- 15 AND-pairs + 20 vote-triples = 35 candidates, deterministic order
    (so re-running a scan produces the same candidate set)."""
    names = sorted(PRIMITIVES.keys())
    candidates = []
    for a, b in itertools.combinations(names, 2):
        candidates.append({
            "label": f"{a}+{b} (AND)",
            "logic": "AND",
            "primitives": [a, b],
            "signal_fn": _make_and_signal(a, b),
        })
    for a, b, c in itertools.combinations(names, 3):
        candidates.append({
            "label": f"{a}+{b}+{c} (2-of-3 vote)",
            "logic": "2-of-3 vote",
            "primitives": [a, b, c],
            "signal_fn": _make_vote_signal(a, b, c),
        })
    return candidates


# ---- sqlite leaderboard ----


def _get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_table():
    conn = _get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS formula_composer_candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            label TEXT NOT NULL,
            logic TEXT NOT NULL,
            primitives TEXT NOT NULL,
            period TEXT NOT NULL,
            n_folds INTEGER NOT NULL,
            in_sample_win_rate_pct REAL,
            in_sample_avg_return_pct REAL,
            in_sample_trade_count INTEGER,
            oos_win_rate_pct REAL,
            oos_avg_return_pct REAL,
            oos_trade_count INTEGER,
            overfitting_risk TEXT,
            overfitting_risk_reason TEXT,
            scanned_at TEXT DEFAULT (datetime('now')),
            UNIQUE(symbol, label)
        )
    """)
    conn.commit()
    conn.close()


_init_table()


def _persist_candidate(symbol: str, cand: Dict, period: str, n_folds: int, result: Dict):
    is_stats = result.get("in_sample", {}).get("stats", {})
    oos_stats = result.get("out_of_sample", {}).get("stats", {})
    conn = _get_db()
    try:
        conn.execute(
            """INSERT INTO formula_composer_candidates
               (symbol, label, logic, primitives, period, n_folds,
                in_sample_win_rate_pct, in_sample_avg_return_pct, in_sample_trade_count,
                oos_win_rate_pct, oos_avg_return_pct, oos_trade_count,
                overfitting_risk, overfitting_risk_reason, scanned_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(symbol, label) DO UPDATE SET
                 logic=excluded.logic, primitives=excluded.primitives,
                 period=excluded.period, n_folds=excluded.n_folds,
                 in_sample_win_rate_pct=excluded.in_sample_win_rate_pct,
                 in_sample_avg_return_pct=excluded.in_sample_avg_return_pct,
                 in_sample_trade_count=excluded.in_sample_trade_count,
                 oos_win_rate_pct=excluded.oos_win_rate_pct,
                 oos_avg_return_pct=excluded.oos_avg_return_pct,
                 oos_trade_count=excluded.oos_trade_count,
                 overfitting_risk=excluded.overfitting_risk,
                 overfitting_risk_reason=excluded.overfitting_risk_reason,
                 scanned_at=excluded.scanned_at""",
            (
                symbol, cand["label"], cand["logic"], ",".join(cand["primitives"]),
                period, n_folds,
                is_stats.get("win_rate_pct"), is_stats.get("avg_return_pct"), is_stats.get("trade_count"),
                oos_stats.get("win_rate_pct"), oos_stats.get("avg_return_pct"), oos_stats.get("trade_count"),
                result.get("overfitting_risk"), result.get("overfitting_risk_reason"),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()
    except Exception:
        logger.exception("formula_composer.persist failed for %s / %s", symbol, cand["label"])
    finally:
        conn.close()


def run_scan(symbol: str, period: str = "2y", interval: str = "1d", n_folds: int = 4,
             min_oos_trades: int = 5, top_n: int = 5,
             commission_pct: float = DEFAULT_COMMISSION_PCT,
             slippage_pct: float = DEFAULT_SLIPPAGE_PCT) -> Dict:
    """
    Fetches `symbol`'s history and computes the causal indicator series
    ONCE (not once per candidate -- see BacktestService._walk_forward_core()'s
    docstring for why this split exists), then walk-forward-validates all
    35 candidates from generate_candidates() against it, keeps only
    candidates that (a) fired at least `min_oos_trades` trades in the
    out-of-sample segment (small-sample filter -- composing two/three
    primitives with AND/vote logic further reduces trade frequency vs any
    single primitive, so most candidates on most symbols will fail this)
    and (b) were not flagged "high" overfitting risk, ranks survivors by
    out-of-sample avg_return_pct, persists every TESTED candidate's result
    to the leaderboard table (not just the survivors, so a symbol that
    found nothing passable is still visibly "scanned, 0 passed" rather
    than silently absent), and returns the top `top_n`.
    """
    symbol = (symbol or "").upper().strip()
    if not symbol:
        return {"error": "缺少代號"}
    n_folds = max(2, int(n_folds))

    try:
        df = _svc._fetch_history(symbol, period, interval)
    except Exception as e:
        return {"error": f"攞唔到 {symbol} 嘅歷史數據：{str(e)}"}

    min_bars = WARMUP_BARS + 10 * n_folds
    if df is None or df.empty or len(df) < min_bars:
        return {"error": f"{symbol} 歷史數據不足，無法做組合掃描（需要至少 {min_bars} 條K線）"}

    df = df.dropna()
    closes, highs, lows, volume = df["Close"], df["High"], df["Low"], df["Volume"]
    ind = BacktestService._compute_causal_indicators(closes, highs, lows, volume)

    candidates = generate_candidates()
    tested: List[Dict] = []
    for cand in candidates:
        result = BacktestService._walk_forward_core(
            df, ind, cand["signal_fn"], cand["label"], symbol,
            period=period, interval=interval, n_folds=n_folds,
            commission_pct=commission_pct, slippage_pct=slippage_pct,
        )
        if "error" in result:
            continue
        _persist_candidate(symbol, cand, period, n_folds, result)
        oos_stats = result.get("out_of_sample", {}).get("stats", {})
        tested.append({
            "label": cand["label"],
            "logic": cand["logic"],
            "primitives": cand["primitives"],
            "result": result,
            "oos_trade_count": oos_stats.get("trade_count", 0) or 0,
            "oos_avg_return_pct": oos_stats.get("avg_return_pct"),
        })

    passed = [
        t for t in tested
        if t["oos_trade_count"] >= min_oos_trades
        and t["result"].get("overfitting_risk") != "high"
    ]
    passed.sort(key=lambda t: (t["oos_avg_return_pct"] if t["oos_avg_return_pct"] is not None else -1e9),
                reverse=True)
    top = passed[:top_n]

    return {
        "symbol": symbol,
        "period": period,
        "n_folds": n_folds,
        "candidates_tested": len(tested),
        "candidates_passed_filter": len(passed),
        "min_oos_trades": min_oos_trades,
        "top": [
            {
                "label": t["label"],
                "logic": t["logic"],
                "primitives": t["primitives"],
                "in_sample": t["result"]["in_sample"],
                "out_of_sample": t["result"]["out_of_sample"],
                "overfitting_risk": t["result"]["overfitting_risk"],
                "overfitting_risk_reason": t["result"]["overfitting_risk_reason"],
            }
            for t in top
        ],
        "caveats": [
            "呢個係喺已有嘅6個因果指標訊號（trend/RSI/MACD/Bollinger/OBV/Donchian）之上做嘅細規模組合（AND/多數表決），"
            "唔係窮舉優化或者機器學習擬合——冇任何參數係根據呢段歷史數據調校出嚟嘅。",
            "組合邏輯（要兩個或以上訊號同時同意）令交易次數進一步減少，已用 min_oos_trades 過濾樣本太細嘅組合，"
            "但留低嘅組合都應該再睇返 out_of_sample.stats.trade_count 嘅實際數值。",
            "只保留 overfitting_risk 唔係「high」嘅組合，但呢個heuristic唔係統計證明，過去表現亦唔代表將來結果，唔係投資建議。",
        ],
    }


def get_leaderboard(symbol: Optional[str] = None, limit: int = 20) -> List[Dict]:
    """Reads the persisted per-(symbol,label) leaderboard, most recently
    scanned first by default; pass `symbol` to scope to one ticker
    (returns its last scan's full 35-candidate table, best first)."""
    conn = _get_db()
    try:
        where = ""
        params: List = []
        if symbol:
            where = "WHERE symbol = ?"
            params.append(symbol.upper().strip())
        rows = conn.execute(
            f"""SELECT * FROM formula_composer_candidates {where}
                ORDER BY (oos_avg_return_pct IS NULL), oos_avg_return_pct DESC, scanned_at DESC
                LIMIT ?""",
            params + [limit],
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
