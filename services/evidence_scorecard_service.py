"""
Multi-Dimensional Evidence Scorecard -- 2026-09-29 (AJ: "XFINLAB要加入多維度
反證去判斷分析市場不同資產，最好有7個以上").

What "反證" (counter-evidence / falsification) means here, stated up front:
this is NOT another confirmation-bias stack of correlated technical
indicators (this codebase already has that -- technical_analysis_service's
own confluence score blends 6 price-based signals into ONE of the
dimensions below). The point of this module is to pull independent
signals from genuinely DIFFERENT domains (price action, company
fundamentals, institutional/insider positioning, derivatives positioning,
macro capital flows, news sentiment, and a backtested statistical model)
and report where they AGREE and where they genuinely DISAGREE -- a
disagreement across independent domains is real counter-evidence a
same-domain indicator stack can never surface, and this module never
hides it to make a cleaner-looking score.

Eleven dimensions are wired below, each already backed by a real,
existing XFINLAB data source (nothing here computes a new indicator from
scratch -- every dimension just asks an existing, already-vetted service
"what does your data say" and translates that into support/oppose/
neutral). Four are STOCK-ONLY because the underlying data genuinely
doesn't exist for other asset classes -- SEC 13F/13D-G/Form-4 filings
and XBRL financial statements are equity-market-specific by nature, not
an XFINLAB coverage gap:
  - fundamentals (revenue growth, from SEC XBRL)
  - institutional_conviction (13F holder conviction score)
  - activist_filings (13D/13G filings)
  - insider_trading (Form 4 buy/sell)
The other seven work for ANY symbol/asset_class (technical_trend, and
six others), though several of them (volatility_regime, capital_flow,
shipping_proxy) are shared MARKET-WIDE context rather than per-symbol --
that's honest, not a placeholder: VIX term structure and capital-flow
risk appetite genuinely don't have a separate reading "for AAPL" vs "for
BTC", they're conditions the whole market operates under.

Consequence, stated honestly rather than glossed over: a stock will
typically have 8-11 available dimensions; crypto/forex/commodities/
futures/indices will typically have 5-7, since they lose the four
stock-only ones (and futures_positioning/direction_probability are
themselves further gated by real per-symbol data existing -- e.g.
CFTC's ticker map only covers ~9 tickers, and direction_probability
only serves symbols with an already-trained, backtest-validated model).
A dimension that doesn't apply is EXCLUDED from the denominator, never
counted as a fabricated "neutral" -- see get_evidence_scorecard()'s
docstring.

Every dimension function below is independently try/except-wrapped and
returns None on ANY failure or inapplicability (same best-effort
contract every other service in this codebase already follows) --
one dimension's data outage never breaks the other ten.
"""

import json
import logging
import os
import sqlite3
from datetime import date
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 2026-09-30 (AJ: monetization gap-analysis session -- "Research Verification
# /Audit Trail" was the second concrete gap identified, after the
# Relationship/Impact API. Exact same day-over-day snapshot+diff pattern
# services/company_network_service.py already established for its own
# `what_changed` field (INSERT...ON CONFLICT upsert, most-recent-prior-date
# lookup, pure mechanical delta computation, no AI, best-effort/never-raise).
# Reused here rather than reinvented so both services behave identically to
# an integrator who's already seen one of them.
#
# What this adds beyond company_network's numeric-only deltas: since each
# evidence-scorecard dimension carries a categorical signal (support/oppose/
# neutral), the diff also surfaces WHICH specific dimensions flipped and
# how (dimension_changes) -- e.g. "news_sentiment flipped oppose->support
# since yesterday" -- not just that the aggregate confluence_pct moved. This
# is the literal answer to "did AI's research verdict change, and why" that
# a plain re-run of the same endpoint can't show on its own.
# ---------------------------------------------------------------------------
_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "xfinlab.db")


def _get_db():
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_snapshot_table():
    conn = _get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS evidence_scorecard_snapshots (
            symbol TEXT NOT NULL,
            asset_class TEXT NOT NULL,
            snapshot_date TEXT NOT NULL,
            confluence_pct REAL,
            support_count INTEGER,
            oppose_count INTEGER,
            neutral_count INTEGER,
            dimensions_available INTEGER,
            has_disagreement INTEGER,
            dimensions_json TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (symbol, asset_class, snapshot_date)
        )
    """)
    conn.commit()
    conn.close()


_init_snapshot_table()


def _save_snapshot_and_diff(symbol: str, asset_class: str, result: Dict) -> Dict:
    """Upserts today's scorecard as a snapshot row, then diffs it against
    the most recent PRIOR date's snapshot for the same (symbol,
    asset_class) -- same "most recent strictly-before-today row" lookup
    company_network_service.py's _save_snapshot_and_diff() uses. Returns
    {"available": False, "message": "..."} if there's no prior snapshot
    yet (first time this symbol/asset_class was ever scored, or it was
    already scored once today with nothing to compare against) or on
    any DB error -- never raises, so a persistence hiccup can only ever
    cost the `what_changed` field, never break the scorecard response
    itself."""
    try:
        conn = _get_db()
        today = date.today().isoformat()
        dims_json = json.dumps(result.get("dimensions") or [])
        conn.execute(
            """INSERT INTO evidence_scorecard_snapshots
               (symbol, asset_class, snapshot_date, confluence_pct, support_count, oppose_count,
                neutral_count, dimensions_available, has_disagreement, dimensions_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(symbol, asset_class, snapshot_date) DO UPDATE SET
                 confluence_pct=excluded.confluence_pct,
                 support_count=excluded.support_count,
                 oppose_count=excluded.oppose_count,
                 neutral_count=excluded.neutral_count,
                 dimensions_available=excluded.dimensions_available,
                 has_disagreement=excluded.has_disagreement,
                 dimensions_json=excluded.dimensions_json""",
            (symbol, asset_class, today, result.get("confluence_pct"), result.get("support_count"),
             result.get("oppose_count"), result.get("neutral_count"), result.get("dimensions_available"),
             int(bool(result.get("has_disagreement"))), dims_json),
        )
        conn.commit()

        prior = conn.execute(
            """SELECT * FROM evidence_scorecard_snapshots
               WHERE symbol=? AND asset_class=? AND snapshot_date<?
               ORDER BY snapshot_date DESC LIMIT 1""",
            (symbol, asset_class, today),
        ).fetchone()
        conn.close()

        if not prior:
            return {
                "available": False,
                "message": "No prior snapshot to compare against yet -- first time this "
                            "symbol/asset_class combination was checked (or already checked "
                            "once today, with nothing new to diff against).",
            }

        def _delta(new_v, old_v):
            if new_v is None or old_v is None:
                return None
            d = new_v - old_v
            return round(d, 2) if isinstance(d, float) else d

        prior_dims = {d["dimension"]: d["signal"] for d in json.loads(prior["dimensions_json"] or "[]")}
        now_dims_list = result.get("dimensions") or []
        now_dims = {d["dimension"]: d["signal"] for d in now_dims_list}
        label_lookup = {d["dimension"]: d["label"] for d in now_dims_list}

        dimension_changes = []
        for dim_key in sorted(set(prior_dims) | set(now_dims)):
            was, now = prior_dims.get(dim_key), now_dims.get(dim_key)
            if was != now:
                dimension_changes.append({
                    "dimension": dim_key,
                    "label": label_lookup.get(dim_key, dim_key),
                    "was_signal": was,   # None means this dimension wasn't available yesterday
                    "now_signal": now,   # None means it's no longer available today
                })

        return {
            "available": True,
            "compared_to_date": prior["snapshot_date"],
            "confluence_pct_delta": _delta(result.get("confluence_pct"), prior["confluence_pct"]),
            "support_count_delta": _delta(result.get("support_count"), prior["support_count"]),
            "oppose_count_delta": _delta(result.get("oppose_count"), prior["oppose_count"]),
            "neutral_count_delta": _delta(result.get("neutral_count"), prior["neutral_count"]),
            "has_disagreement_changed": bool(result.get("has_disagreement")) != bool(prior["has_disagreement"]),
            "dimension_changes": dimension_changes,
        }
    except Exception:
        return {"available": False, "message": "Snapshot/diff unavailable this run."}

STOCK_ONLY_DIMENSIONS = {"fundamentals", "institutional_conviction", "activist_filings", "insider_trading"}

ALL_DIMENSION_LABELS = {
    "technical_trend": "技術面走勢共識（Confluence）",
    "fundamentals": "基本面營收增長（SEC XBRL）",
    "institutional_conviction": "機構持倉Conviction（13F）",
    "activist_filings": "大戶13D/13G申報",
    "insider_trading": "內部人交易（Form 4）",
    "volatility_regime": "VIX波幅期限結構（市場層面）",
    "futures_positioning": "CFTC COT投機者持倉",
    "capital_flow": "宏觀資金流向／風險偏好（市場層面）",
    "shipping_proxy": "航運/供應鏈代理指標（市場層面）",
    "news_sentiment": "新聞情緒（FinBERT）",
    "direction_probability": "ML方向機率模型（含真實往績）",
}


def _dim_technical_trend(symbol: str) -> Optional[Dict]:
    try:
        from services.technical_analysis_service import get_technical_analysis_raw_and_translated
        raw, _ = get_technical_analysis_raw_and_translated(symbol)
        if not raw or "error" in raw:
            return None
        confluence = raw.get("confluence") or {}
        direction = confluence.get("direction")
        if direction == "偏多":
            signal = "support"
        elif direction == "偏空":
            signal = "oppose"
        elif direction == "訊號分歧，中性":
            signal = "neutral"
        else:
            return None  # "數據不足" or missing -- honestly unavailable, not neutral
        return {
            "dimension": "technical_trend", "label": ALL_DIMENSION_LABELS["technical_trend"],
            "signal": signal, "detail": f"confluence={direction} (score={confluence.get('score')})",
        }
    except Exception:
        return None


def _dim_fundamentals(symbol: str) -> Optional[Dict]:
    try:
        from services.fundamentals_service import get_fundamentals
        f = get_fundamentals(symbol)
        growth = f.get("revenue_growth_pct") if f else None
        if growth is None:
            return None
        signal = "support" if growth > 3 else "oppose" if growth < -3 else "neutral"
        return {
            "dimension": "fundamentals", "label": ALL_DIMENSION_LABELS["fundamentals"],
            "signal": signal, "detail": f"revenue_growth_pct={growth}%",
        }
    except Exception:
        return None


def _dim_institutional_conviction(symbol: str) -> Optional[Dict]:
    try:
        from services.sec_ownership_service import get_conviction_score
        c = get_conviction_score(symbol)
        if not c.get("available"):
            return None
        score = c.get("score")
        if score is None:
            return None
        # Asymmetric on purpose: a LOW score means "not tracked/held", not
        # "institutions are bearish" -- this dataset never observes actual
        # selling, only current holding, so it can only ever support or
        # stay neutral, never oppose (that would be fabricating a signal
        # the data doesn't contain).
        signal = "support" if score >= 60 else "neutral"
        return {
            "dimension": "institutional_conviction", "label": ALL_DIMENSION_LABELS["institutional_conviction"],
            "signal": signal, "detail": f"conviction_score={score}/100",
        }
    except Exception:
        return None


def _dim_activist_filings(symbol: str) -> Optional[Dict]:
    try:
        from services.sec_13d_13g_service import search_recent_filings
        r = search_recent_filings(symbol)
        if not r.get("available"):
            return None
        filings = r.get("filings") or []
        if not filings:
            return None
        has_13d = any("13D" in (f.get("form_type") or "").upper() for f in filings)
        signal = "support" if has_13d else "neutral"
        return {
            "dimension": "activist_filings", "label": ALL_DIMENSION_LABELS["activist_filings"],
            "signal": signal, "detail": f"{len(filings)} recent filing(s), activist_13D={has_13d}",
        }
    except Exception:
        return None


def _dim_insider_trading(symbol: str) -> Optional[Dict]:
    try:
        from services.sec_form4_service import get_recent_insider_transactions
        r = get_recent_insider_transactions(symbol)
        if not r.get("available"):
            return None
        summary = r.get("summary") or {}
        net_value = summary.get("net_value_usd")
        if net_value is None:
            return None
        signal = "support" if net_value > 0 else "oppose" if net_value < 0 else "neutral"
        return {
            "dimension": "insider_trading", "label": ALL_DIMENSION_LABELS["insider_trading"],
            "signal": signal, "detail": f"net_value_usd={net_value}",
        }
    except Exception:
        return None


def _dim_volatility_regime() -> Optional[Dict]:
    """Market-wide, not per-symbol -- see module docstring."""
    try:
        from services.cboe_vix_service import get_snapshot
        v = get_snapshot()
        if not v.get("available"):
            return None
        structure = v.get("structure")
        if structure == "backwardation":
            signal = "oppose"  # near-term fear priced above long-term -- risk-off
        elif structure == "contango":
            signal = "support"  # normal calm term structure -- risk-on
        elif structure == "flat":
            signal = "neutral"
        else:
            return None
        return {
            "dimension": "volatility_regime", "label": ALL_DIMENSION_LABELS["volatility_regime"],
            "signal": signal, "detail": f"vix_term_structure={structure}",
        }
    except Exception:
        return None


def _dim_futures_positioning(symbol: str) -> Optional[Dict]:
    try:
        from services.cftc_cot_service import get_cot_for_ticker
        c = get_cot_for_ticker(symbol)
        if not c:
            return None
        net_noncomm = c.get("net_noncomm")
        if net_noncomm is None:
            return None
        signal = "support" if net_noncomm > 0 else "oppose" if net_noncomm < 0 else "neutral"
        return {
            "dimension": "futures_positioning", "label": ALL_DIMENSION_LABELS["futures_positioning"],
            "signal": signal,
            "detail": f"net_noncommercial_contracts={net_noncomm} ({c.get('match_type')} match via {c.get('matched_ticker')})",
        }
    except Exception:
        return None


def _dim_capital_flow() -> Optional[Dict]:
    """Market-wide, not per-symbol -- see module docstring."""
    try:
        from services.capital_flow_engine import get_capital_flow_signal_for_confluence
        c = get_capital_flow_signal_for_confluence()
        if not c:
            return None
        direction = c.get("direction") or ""
        if "淨流入" in direction:
            signal = "support"
        elif "淨流出" in direction:
            signal = "oppose"
        elif "分歧" in direction:
            signal = "neutral"
        else:
            return None
        return {
            "dimension": "capital_flow", "label": ALL_DIMENSION_LABELS["capital_flow"],
            "signal": signal, "detail": f"{direction} (score={c.get('score')})",
        }
    except Exception:
        return None


def _dim_shipping_proxy() -> Optional[Dict]:
    """Market-wide, not per-symbol -- see module docstring. Most directly
    relevant to trade-sensitive assets (commodities/industrials), but
    included for every asset class as loose macro context rather than
    hand-picking which classes "deserve" it."""
    try:
        from services.shipping_proxy_service import get_shipping_proxy
        s = get_shipping_proxy()
        if not s.get("available"):
            return None
        trend = s.get("combined_trend")
        if trend == "RISING":
            signal = "support"
        elif trend == "FALLING":
            signal = "oppose"
        elif trend in ("FLAT", "MIXED"):
            signal = "neutral"
        else:
            return None
        return {
            "dimension": "shipping_proxy", "label": ALL_DIMENSION_LABELS["shipping_proxy"],
            "signal": signal, "detail": f"BDRY/BOAT combined_trend={trend}",
        }
    except Exception:
        return None


def _dim_news_sentiment(symbol: str, display_name: Optional[str] = None) -> Optional[Dict]:
    try:
        from services.news_service import NewsService
        from services.finbert_sentiment_service import analyze_batch
        articles = NewsService().get_company_news(display_name or symbol)
        if not articles:
            return None
        titles = [a.get("title", "") for a in articles if a.get("title")]
        if not titles:
            return None
        result = analyze_batch(titles[:10])
        if not result.get("available"):
            return None
        results = result.get("results") or []
        if not results:
            return None
        total = len(results)
        pos = sum(1 for r in results if r.get("label") == "positive")
        neg = sum(1 for r in results if r.get("label") == "negative")
        if pos > neg and pos / total >= 0.4:
            signal = "support"
        elif neg > pos and neg / total >= 0.4:
            signal = "oppose"
        else:
            signal = "neutral"
        return {
            "dimension": "news_sentiment", "label": ALL_DIMENSION_LABELS["news_sentiment"],
            "signal": signal, "detail": f"{pos} positive / {neg} negative / {total} headlines analyzed",
        }
    except Exception:
        return None


def _dim_direction_probability(symbol: str) -> Optional[Dict]:
    try:
        from services.direction_probability_service import get_direction_probability
        d = get_direction_probability(symbol)
        if not d.get("available"):
            return None
        pct = d.get("up_probability_pct")
        if pct is None:
            return None
        signal = "support" if pct >= 55 else "oppose" if pct <= 45 else "neutral"
        return {
            "dimension": "direction_probability", "label": ALL_DIMENSION_LABELS["direction_probability"],
            "signal": signal,
            "detail": f"up_probability_pct={pct}% (holdout_accuracy={d.get('holdout_accuracy_pct')}%)",
        }
    except Exception:
        return None


def get_evidence_scorecard(symbol: str, asset_class: str = "Stocks", display_name: Optional[str] = None) -> Dict:
    """Runs every dimension applicable to `asset_class`, tallies real
    support/oppose/neutral counts among the ones that actually returned
    data, and -- the whole point of "反證" -- explicitly flags when
    independent domains disagree (has_disagreement) rather than letting
    a blended score quietly average a real conflict away.

    `dimensions_checked` vs `dimensions_available`: checked is always the
    same fixed count for a given asset_class (11 for Stocks, 7 for
    everything else); available is however many of those actually
    returned real data for THIS symbol right now. The gap between them
    is never hidden -- see `dimensions_skipped` and the honesty note in
    the response.

    `confluence_pct`: support / (support + oppose), i.e. among dimensions
    that took a side at all (neutral and unavailable both excluded from
    this specific ratio, since neither one is evidence for either side).
    None if there were zero directional (support or oppose) dimensions.

    Never raises -- every _dim_*() call is already independently
    try/except-wrapped."""
    symbol = (symbol or "").upper().strip()
    asset_class = (asset_class or "Stocks").strip()
    is_stock = asset_class.lower() == "stocks"

    checks = [_dim_technical_trend(symbol)]
    if is_stock:
        checks += [
            _dim_fundamentals(symbol),
            _dim_institutional_conviction(symbol),
            _dim_activist_filings(symbol),
            _dim_insider_trading(symbol),
        ]
    checks += [
        _dim_volatility_regime(),
        _dim_futures_positioning(symbol),
        _dim_capital_flow(),
        _dim_shipping_proxy(),
        _dim_news_sentiment(symbol, display_name),
        _dim_direction_probability(symbol),
    ]

    available = [c for c in checks if c]
    support = [c for c in available if c["signal"] == "support"]
    oppose = [c for c in available if c["signal"] == "oppose"]
    neutral = [c for c in available if c["signal"] == "neutral"]
    directional_total = len(support) + len(oppose)

    scorecard = {
        "symbol": symbol,
        "asset_class": asset_class,
        "dimensions_checked": len(checks),
        "dimensions_available": len(available),
        "dimensions_skipped": len(checks) - len(available),
        "support_count": len(support),
        "oppose_count": len(oppose),
        "neutral_count": len(neutral),
        "confluence_pct": round(len(support) / directional_total * 100, 1) if directional_total else None,
        "has_disagreement": len(support) > 0 and len(oppose) > 0,
        "dimensions": available,
        "note": (
            "每個維度嚟自獨立真實data source，唔係AI猜測。dimensions_available"
            "細過dimensions_checked係正常現象（例如13F/內部人交易淨係stock先有，"
            "crypto/forex/commodity/futures/indices本身冇呢類data，誠實跳過"
            "而唔係屈個假訊號）。has_disagreement=true代表唔同獨立維度出現矛盾"
            "訊號，呢個先至係「反證」嘅重點——唔應該用嚟做投資決定，僅供參考。"
        ),
    }
    # 2026-09-30: day-over-day audit trail -- see _save_snapshot_and_diff()'s
    # docstring above. Persists this call's result as today's snapshot and
    # diffs it against the most recent prior day, so a repeat caller can see
    # not just today's scorecard but WHAT CHANGED (and which specific
    # dimensions flipped) since last time, without maintaining their own
    # history. Wrapped by _save_snapshot_and_diff itself, never raises.
    scorecard["what_changed"] = _save_snapshot_and_diff(symbol, asset_class, scorecard)
    return scorecard
