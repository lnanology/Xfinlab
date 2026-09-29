#!/usr/bin/env python3
"""
XFINLAB Direction Probability Model -- Training/Retraining Job.

Runs services/direction_probability_service.py's train_and_backtest() for
every symbol in a watchlist and prints the outcome. This is the "定期重新
訓練基建" (periodic retraining infrastructure) the Stage 2 roadmap item
called for -- meant to be run periodically (e.g. monthly, matching
MODEL_MAX_AGE_DAYS in direction_probability_service.py) via a scheduled
job, the same way scripts/security_scan.py runs on a schedule rather than
inline in a live request.

NOT run automatically as part of THIS sandboxed session: it needs real
network access to fetch live OHLCV history for each symbol (via
services/technical_analysis_service.fetch_ohlc_history()'s Alpaca-first/
yfinance-fallback routing), which this dev environment doesn't have. The
service module's own honesty gate (a one-sided binomial significance
test against the naive majority-class baseline, evaluated on a
genuinely independent/non-overlapping holdout -- see that module's
docstring) was instead validated with synthetic data before this script
was written, confirming it correctly rejects pure-noise data and
correctly accepts data with real injected structure.

2026-09-29 (AJ: "一次過起晒" -- step 3 of the prediction-ledger/learning-
loop request): retrain_all() below is now called automatically on a
monthly cron from backend/main.py (see _run_direction_model_retrain_job
there), matching MODEL_MAX_AGE_DAYS. Production (Railway) DOES have the
real network access this sandbox lacks, so the automation is real even
though it couldn't be exercised end-to-end here. Refactored the CLI's
inline logic out into retrain_all() so the scheduled job and this CLI
call the exact same code path -- no separate "job version" to drift
out of sync with the version a human runs by hand.

Deliberately reuses growth/reddit_bot.py's WATCHLIST rather than
maintaining a second, separately-drifting symbol list.

Usage:
    python3 scripts/train_direction_models.py [--horizon 5] [--period 2y] [--symbols AAPL,MSFT]
"""

import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.direction_probability_service import train_and_backtest, DEFAULT_HORIZON_DAYS


def retrain_all(horizon_days: int = DEFAULT_HORIZON_DAYS, period: str = "2y", symbols=None, log=print) -> dict:
    """Retrains+backtests every symbol in `symbols` (default: growth/
    reddit_bot.py's WATCHLIST, imported lazily here so importing this
    module -- e.g. from the scheduled job -- doesn't pull in Reddit-bot
    dependencies unless this actually runs). `log` defaults to print()
    for the CLI; the scheduled job passes logger.info instead so this
    shows up in Railway logs rather than going nowhere. Returns a
    summary dict rather than just printing, so a caller (the scheduled
    job, a future admin-panel button) can act on the result instead of
    scraping stdout."""
    if symbols is None:
        from growth.reddit_bot import RedditBot
        symbols = RedditBot.WATCHLIST

    log(f"XFINLAB Direction Probability -- training {len(symbols)} symbols, horizon={horizon_days}d, period={period}")

    validated_count = 0
    results = []
    for symbol in symbols:
        try:
            result = train_and_backtest(symbol, horizon_days=horizon_days, period=period)
        except Exception as e:
            result = {"available": False, "message": f"未預期錯誤：{e}"}
        results.append((symbol, result))

        if not result.get("available"):
            log(f"  {symbol}: SKIPPED -- {result.get('message')}")
            continue

        status = "VALIDATED" if result["validated"] else "rejected (failed backtest gate)"
        log(
            f"  {symbol}: {status} -- holdout_acc={result['holdout_accuracy_pct']}% "
            f"baseline={result['baseline_accuracy_pct']}% p={result['p_value']} "
            f"(n_train={result['n_train_samples']}, n_holdout={result['n_holdout_samples']})"
        )
        if result["validated"]:
            validated_count += 1

    log(f"Done: {validated_count}/{len(symbols)} symbols passed the backtest gate and will be served by predict().")
    return {"total": len(symbols), "validated": validated_count, "results": results}


def main():
    parser = argparse.ArgumentParser(description="Train/retrain XFINLAB direction probability models")
    parser.add_argument("--horizon", type=int, default=DEFAULT_HORIZON_DAYS, help="Prediction horizon in trading days")
    parser.add_argument("--period", type=str, default="2y", help="History window to fetch per symbol (yfinance/Alpaca period string)")
    parser.add_argument("--symbols", type=str, default=None, help="Comma-separated symbol override (default: growth/reddit_bot.py's WATCHLIST)")
    args = parser.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",")] if args.symbols else None
    retrain_all(horizon_days=args.horizon, period=args.period, symbols=symbols)


if __name__ == "__main__":
    main()
