"""
Track Record Service -- aggregate real backtest statistics for the
homepage's honest "Track Record" section (2026-07-23, psychology
differentiation batch).

Reuses services/backtest_service.py's BacktestService.run() (real
backtest over real Alpaca/yfinance historical data, no look-ahead bias --
see that module's own docstring for the full methodology and caveats)
against api/market_pulse.py's EXISTING _PULSE_BASKET (SPY/QQQ/DIA/IWM/
XLK/XLF/XLE/BTC-USD) -- the same fixed, already-audited 8-ticker universe
already used for the homepage's Market Pulse widget. Reused here rather
than a fresh basket hand-picked for this feature, so there is no risk of
silently cherry-picking whichever tickers happen to backtest best for a
marketing number.

Strategy fixed to "confluence_trend" -- the live, user-facing strategy
this platform's Decision Score/Confluence Engine actually uses, not
whichever of BacktestService.STRATEGIES scores highest (that would be
survivorship-bias-by-selection, the same failure mode BacktestService.
compare()'s own disclaimer warns about).

Cached in-process with a 24-hour TTL: an 8-ticker x 2-year backtest is a
few seconds of work, not something to redo on every homepage visitor --
same lazy-recompute-on-stale-read pattern already used by api/market_
pulse.py's _compute_pulse()/_compute_free_signals() caches.

Every response carries the same style of honesty caveats as
BacktestService.run() itself -- this number is a historical backtest,
not a live trading record, and is never allowed to be presented as more
authoritative than that.
"""
import time
from typing import Dict, List, Optional

from services.backtest_service import BacktestService

_BASKET = ["SPY", "QQQ", "DIA", "IWM", "XLK", "XLF", "XLE", "BTC-USD"]
_STRATEGY = "confluence_trend"
_PERIOD = "2y"

_CACHE_TTL_SECONDS = 24 * 3600
_cache: Optional[Dict] = None
_cache_time: float = 0.0


def _compute() -> Dict:
    per_symbol: List[Dict] = []
    total_trades = 0
    weighted_win_sum = 0.0
    # 2026-08-25 (AJ: "移除首頁 38.9% Win Rate -- 或者改成 Sharpe / max
    # drawdown / hit rate by regime，畀context。裸露一個38.9%只會趕客"):
    # a bare win-rate number with nothing else next to it reads as either
    # cherry-picked or naive to anyone who actually trades (win rate alone
    # says nothing about payoff asymmetry or tail risk). Both
    # sharpe_like and max_drawdown_pct were already computed per-symbol
    # by BacktestService.run() and simply never aggregated/surfaced --
    # added here rather than inventing a new metric. Regime-conditioned
    # hit rate is NOT included: doing that honestly would need a
    # historical (not just live-belief) regime classifier per trade
    # date, which services/regime_belief_service.py doesn't provide --
    # rather than fake that breakdown, this ships with the two real
    # numbers that were already sitting there unused.
    weighted_sharpe_sum = 0.0
    sharpe_weight = 0
    worst_max_drawdown_pct = None

    for symbol in _BASKET:
        try:
            result = BacktestService.run(symbol, strategy=_STRATEGY, period=_PERIOD)
        except Exception:
            continue
        if not result or "error" in result:
            continue
        stats = result.get("stats") or {}
        n = stats.get("trade_count") or 0
        wr = stats.get("win_rate_pct")
        sh = stats.get("sharpe_like")
        dd = stats.get("max_drawdown_pct")
        per_symbol.append({
            "symbol": symbol,
            "win_rate_pct": wr,
            "trade_count": n,
            "avg_return_pct": stats.get("avg_return_pct"),
            "sharpe_like": sh,
            "max_drawdown_pct": dd,
        })
        if n and wr is not None:
            total_trades += n
            weighted_win_sum += wr * n
        if n and sh is not None:
            weighted_sharpe_sum += sh * n
            sharpe_weight += n
        if dd is not None:
            # Worst (deepest) observed drawdown across the basket -- NOT
            # averaged. Averaging away the worst symbol's drawdown would
            # understate real tail risk; a homepage risk-context number
            # should be conservative, not flattering.
            worst_max_drawdown_pct = dd if worst_max_drawdown_pct is None else max(worst_max_drawdown_pct, dd)

    overall_win_rate = round(weighted_win_sum / total_trades, 1) if total_trades > 0 else None
    overall_sharpe_like = round(weighted_sharpe_sum / sharpe_weight, 2) if sharpe_weight > 0 else None
    per_symbol.sort(key=lambda r: (r["win_rate_pct"] if r["win_rate_pct"] is not None else -1), reverse=True)

    return {
        "strategy": _STRATEGY,
        "period": _PERIOD,
        "basket": _BASKET,
        "overall_win_rate_pct": overall_win_rate,
        "overall_sharpe_like": overall_sharpe_like,
        "worst_max_drawdown_pct": round(worst_max_drawdown_pct, 2) if worst_max_drawdown_pct is not None else None,
        "total_trades": total_trades,
        "symbols_tested": len(per_symbol),
        "per_symbol": per_symbol,
        "caveats": [
            "呢個係對過去歷史數據嘅回測結果，唔係實際落單交易紀錄，亦唔係未來保證。",
            "已扣除保守假設嘅手續費+滑點（詳見 services/backtest_service.py 嘅 cost_model），"
            "avg_return_pct 係net-of-cost數字，並非未計成本嘅樂觀估算。",
            "樣本基於固定8個大盤/板塊指數（同首頁Market Pulse用緊嘅同一組），並非度身挑選表現最好嘅資產。",
            "細樣本嘅勝率統計學上參考價值有限，請留意 total_trades。",
            "sharpe_like 係逐單交易嘅回報/標準差，唔係年化Sharpe（嗰個需要逐日帳戶回報，呢個模擬未有），"
            "刻意用呢個名避免同真正嘅Sharpe混淆。max_drawdown_pct 係basket入面表現最差果隻嘅最大回撤，"
            "唔係平均數，故意保守。",
        ],
    }


def get_track_record(force_refresh: bool = False) -> Dict:
    """Returns the cached aggregate, recomputing at most once per
    _CACHE_TTL_SECONDS (lazy -- computed on first request after the TTL
    expires, not on a background schedule)."""
    global _cache, _cache_time
    now = time.time()
    if force_refresh or _cache is None or (now - _cache_time) > _CACHE_TTL_SECONDS:
        computed = _compute()
        # Never overwrite a previously-good cache with an all-failed
        # result (e.g. transient data-provider outage) -- stale-but-real
        # beats fresh-but-empty for a homepage trust widget.
        if computed["symbols_tested"] > 0 or _cache is None:
            _cache = computed
            _cache_time = now
    return _cache
