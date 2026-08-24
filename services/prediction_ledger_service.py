"""
Prediction Ledger Service -- P1 of the Quant Research Factory roadmap
(2026-08-10).

Auto-records every real prediction services/direction_probability_service.py
serves (the only place in this codebase that already emits a dated,
ticker-specific, backtested probability -- see that module's docstring),
then a scheduled job grades each one against what actually happened once
its horizon has passed, computing hit rate + Brier score. This is the
"does XFINLAB's research pipeline actually get better over time, and can
we prove it" flywheel from the Quant Research Factory roadmap -- without
this, no amount of downstream strategy-composition work (P2/P3) has any
honest way to demonstrate any of its output is real rather than curve-fit
noise.

Hook point: api/ai_analysis.py calls get_direction_probability(symbol)
once per POST /ai-analysis request; record_prediction() is called right
after that (best-effort, wrapped in try/except by the caller so a ledger
failure never breaks the live response), using the market price already
fetched in that same request and the just-refreshed regime belief
(get_smart_beta() -> regime_belief_service.update_belief() already ran
earlier in that same request for this symbol, so
regime_belief_service.get_belief(symbol) here is a fresh read, not a
stale one -- see the research this module was scoped from).

Design choices, stated up front rather than left implicit:
  - One row per (symbol, predicted_at date, horizon_days, source) --
    ON CONFLICT DO UPDATE, so re-analyzing the same symbol twice in one
    day refreshes "today's prediction" rather than duplicating it. The
    ledger is meant to answer "how good is this model's daily call",
    not to be spammed by repeat page views of the same analysis.
  - Grading uses the CURRENT close price at grading time (fetched fresh
    in grade_pending_predictions()), not a reconstructed "close on day
    predicted_at+horizon_days" -- because the scheduled job only ever
    grades rows once enough calendar days have already elapsed. See
    that function's own docstring for the exact honesty tradeoff this
    makes (calendar days as a proxy for the model's trading-day
    horizon).
  - Brier score component per prediction: (forecast_probability -
    actual_outcome)^2, actual_outcome in {0,1}. Lower is better-
    calibrated; a coin-flip forecast scores 0.25 on average -- the
    reference point quoted in get_ledger_stats()'s note field.
"""

import logging
import os
import sqlite3
from datetime import date, datetime, timezone
from typing import Dict, List, Optional

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "xfinlab.db")

logger = logging.getLogger(__name__)


def _get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_table():
    conn = _get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS prediction_ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            predicted_at TEXT NOT NULL,
            horizon_days INTEGER NOT NULL,
            up_probability_pct REAL NOT NULL,
            predicted_direction TEXT NOT NULL,
            price_at_prediction REAL,
            regime_at_prediction TEXT,
            regime_probability_pct REAL,
            source TEXT NOT NULL DEFAULT 'direction_probability_service',
            graded INTEGER NOT NULL DEFAULT 0,
            graded_at TEXT,
            actual_close REAL,
            actual_return_pct REAL,
            actual_direction TEXT,
            correct INTEGER,
            brier_component REAL,
            created_at TEXT DEFAULT (datetime('now')),
            UNIQUE(symbol, predicted_at, horizon_days, source)
        )
    """)
    conn.commit()
    conn.close()


_init_table()


def record_prediction(symbol: str, direction_result: Optional[Dict],
                       price_at_prediction: Optional[float] = None,
                       regime: Optional[Dict] = None,
                       source: str = "direction_probability_service") -> Optional[Dict]:
    """
    direction_result: the dict returned by
    services.direction_probability_service.get_direction_probability() --
    only records something if direction_result.get("available") is True
    (an unavailable/unvalidated prediction has nothing to grade, so
    logging it would just be noise in the ledger).
    regime: the dict returned by services.regime_belief_service.get_belief(symbol),
    or None if unavailable -- purely informational context stored
    alongside the prediction; grading never depends on it.
    Returns the inserted/updated row as a dict, or None if nothing was
    recorded (missing/unavailable input, or a DB error -- logged, never
    raised, since this must never be allowed to break a live request).
    """
    if not direction_result or not direction_result.get("available"):
        return None
    symbol = (symbol or "").upper().strip()
    if not symbol:
        return None

    up_pct = direction_result.get("up_probability_pct")
    horizon_days = direction_result.get("horizon_days")
    if up_pct is None or horizon_days is None:
        return None

    predicted_direction = "up" if up_pct >= 50 else "down"
    predicted_at = date.today().isoformat()
    top_regime = regime.get("top_regime") if regime else None
    top_regime_pct = regime.get("top_probability_pct") if regime else None

    conn = _get_db()
    try:
        conn.execute(
            """INSERT INTO prediction_ledger
               (symbol, predicted_at, horizon_days, up_probability_pct, predicted_direction,
                price_at_prediction, regime_at_prediction, regime_probability_pct, source)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(symbol, predicted_at, horizon_days, source) DO UPDATE SET
                 up_probability_pct=excluded.up_probability_pct,
                 predicted_direction=excluded.predicted_direction,
                 price_at_prediction=excluded.price_at_prediction,
                 regime_at_prediction=excluded.regime_at_prediction,
                 regime_probability_pct=excluded.regime_probability_pct""",
            (symbol, predicted_at, horizon_days, up_pct, predicted_direction,
             price_at_prediction, top_regime, top_regime_pct, source),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM prediction_ledger WHERE symbol=? AND predicted_at=? AND horizon_days=? AND source=?",
            (symbol, predicted_at, horizon_days, source),
        ).fetchone()
        return dict(row) if row else None
    except Exception:
        logger.exception("prediction_ledger.record_prediction failed for %s", symbol)
        return None
    finally:
        conn.close()


def grade_pending_predictions(calendar_day_buffer: float = 1.4) -> Dict:
    """
    Finds every ungraded row whose horizon has plausibly elapsed --
    (today - predicted_at).days >= horizon_days * calendar_day_buffer --
    and grades it using the CURRENT close price (fetched fresh here),
    not a reconstructed historical close on the exact target date. The
    `calendar_day_buffer` (default 1.4x) exists because horizon_days is
    defined in TRADING days (see direction_probability_service.py) but
    this job runs on calendar-day cadence -- 1.4x roughly covers
    weekends without waiting unnecessarily long past the real target.

    This is a deliberate, documented approximation, not silent
    imprecision: the exact trading-day-N close is not reconstructed
    because by the time grading runs, "N trading days later" and "now"
    are close enough that the small extra drift this introduces rarely
    changes the directional grade, and doing this the fully precise way
    would mean storing/re-deriving a trading calendar per symbol for a
    marginal Brier-score precision gain, not a correctness gain.

    Returns {"graded": int, "errors": int, "skipped_too_recent": int}.
    """
    from services.technical_analysis_service import fetch_ohlc_history

    conn = _get_db()
    try:
        pending = conn.execute("SELECT * FROM prediction_ledger WHERE graded = 0").fetchall()
    finally:
        conn.close()

    graded, errors, too_recent = 0, 0, 0
    today = date.today()

    for row in pending:
        try:
            predicted_at = date.fromisoformat(row["predicted_at"])
        except Exception:
            errors += 1
            continue
        elapsed_days = (today - predicted_at).days
        if elapsed_days < row["horizon_days"] * calendar_day_buffer:
            too_recent += 1
            continue

        symbol = row["symbol"]
        price_then = row["price_at_prediction"]
        if price_then is None or price_then <= 0:
            errors += 1
            continue

        try:
            df = fetch_ohlc_history(symbol, period="5d", interval="1d")
            if df is None or df.empty:
                errors += 1
                continue
            actual_close = float(df["Close"].iloc[-1])
        except Exception:
            logger.exception("prediction_ledger.grade_pending_predictions: fetch failed for %s", symbol)
            errors += 1
            continue

        actual_return_pct = (actual_close - price_then) / price_then * 100
        actual_direction = "up" if actual_return_pct > 0 else "down"
        correct = int(actual_direction == row["predicted_direction"])
        actual_outcome = 1.0 if actual_direction == "up" else 0.0
        forecast_prob = row["up_probability_pct"] / 100.0
        brier_component = (forecast_prob - actual_outcome) ** 2

        conn2 = _get_db()
        try:
            conn2.execute(
                """UPDATE prediction_ledger SET
                     graded=1, graded_at=?, actual_close=?, actual_return_pct=?,
                     actual_direction=?, correct=?, brier_component=?
                   WHERE id=?""",
                (
                    datetime.now(timezone.utc).isoformat(), actual_close,
                    round(actual_return_pct, 3), actual_direction, correct,
                    round(brier_component, 4), row["id"],
                ),
            )
            conn2.commit()
            graded += 1
        except Exception:
            logger.exception("prediction_ledger.grade_pending_predictions: update failed for row %s", row["id"])
            errors += 1
        finally:
            conn2.close()

    return {"graded": graded, "errors": errors, "skipped_too_recent": too_recent}


def get_ledger_stats(symbol: Optional[str] = None, source: Optional[str] = None) -> Dict:
    """Aggregate accuracy stats over all GRADED predictions (optionally
    filtered to one symbol and/or one source). This is the honesty
    scoreboard the module docstring describes -- hit_rate_pct and
    avg_brier_score are the two numbers that actually answer "is this
    model any good", as opposed to a backtest's own self-reported
    holdout_accuracy_pct.
    2026-08-24: added `source` filter so multiple ledger-writers sharing
    this one table (direction_probability_service,
    capital_flow_forecast, ...) can each be scored separately -- e.g.
    admin.py's /admin/prediction-ledger?source=capital_flow_forecast --
    without one source's volume drowning out another's in a blended
    number."""
    conn = _get_db()
    try:
        where = "WHERE graded = 1"
        params: List = []
        if symbol:
            where += " AND symbol = ?"
            params.append(symbol.upper().strip())
        if source:
            where += " AND source = ?"
            params.append(source.strip())
        rows = conn.execute(f"SELECT * FROM prediction_ledger {where}", params).fetchall()

        pending_where = "WHERE graded = 0"
        pending_params: List = []
        if symbol:
            pending_where += " AND symbol = ?"
            pending_params.append(symbol.upper().strip())
        if source:
            pending_where += " AND source = ?"
            pending_params.append(source.strip())
        pending_count = conn.execute(
            f"SELECT COUNT(*) as c FROM prediction_ledger {pending_where}", pending_params
        ).fetchone()["c"]
    finally:
        conn.close()

    n = len(rows)
    if n == 0:
        return {
            "graded_count": 0,
            "pending_count": pending_count,
            "hit_rate_pct": None,
            "avg_brier_score": None,
            "avg_actual_return_pct": None,
            "note": "仲未有已評分嘅預測，回頭嚟睇。",
        }

    hits = sum(r["correct"] for r in rows if r["correct"] is not None)
    briers = [r["brier_component"] for r in rows if r["brier_component"] is not None]
    returns = [r["actual_return_pct"] for r in rows if r["actual_return_pct"] is not None]

    return {
        "graded_count": n,
        "pending_count": pending_count,
        "hit_rate_pct": round(hits / n * 100, 1),
        "avg_brier_score": round(sum(briers) / len(briers), 4) if briers else None,
        "avg_actual_return_pct": round(sum(returns) / len(returns), 2) if returns else None,
        "note": (
            "hit_rate_pct係預測方向啱嘅比例（up/down預測 vs 實際）；avg_brier_score越接近0代表機率校準越準"
            "（0.25係亂猜嘅參考水平）。細樣本統計學上唔可靠，請留意 graded_count。"
        ),
    }


def get_recent_predictions(limit: int = 50, symbol: Optional[str] = None, source: Optional[str] = None) -> List[Dict]:
    conn = _get_db()
    try:
        clauses: List[str] = []
        params: List = []
        if symbol:
            clauses.append("symbol = ?")
            params.append(symbol.upper().strip())
        if source:
            clauses.append("source = ?")
            params.append(source.strip())
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        rows = conn.execute(
            f"SELECT * FROM prediction_ledger {where} ORDER BY predicted_at DESC, id DESC LIMIT ?",
            params + [limit],
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
