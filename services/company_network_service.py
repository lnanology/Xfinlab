"""
Company Network Intelligence -- 2026-08-29 (AJ: "做啦" after the
Company/Business Intelligence scoping conversation).

What this is: Phase 1 of the "Company Intelligence" direction -- combines
FOUR already-collected Data Factory signals into one relationship view for
a ticker: who owns it (SEC 13F institutional holders), who's trying to
influence it (SEC 13D/13G activist filings), who's trading it from the
inside (SEC Form 4 insiders), and whether it has a directly linked futures
market (CFTC COT). Deliberately ZERO new data sources -- every field here
is a direct pass-through or simple aggregation of services already built
and already live in the Confluence Engine
(services/technical_analysis_service.py). This module does not re-fetch or
re-parse anything; it only re-packages.

Honesty posture, matching every other Data Factory/Intelligence API module
in this codebase: no fabricated scores. `network_summary` only ever
surfaces counts, sums, and pass-through values that are directly traceable
to a row in sec_13f_holdings / sec_13d_13g_filings / sec_form4_transactions
/ cftc_cot_observations. There is no synthetic "dependency score" or
"fragility score" here -- deliberately rejected per the scoping
conversation (those numbers would require real supply-chain/physical-world
data XFINLAB does not have; presenting a confident-looking 0-100 number
without that underlying data would break the exact "no fabricated numbers"
promise this API is built on).

"What changed?" (company_network_snapshots table below): every call
persists today's network_summary numbers, then diffs against the most
recent PRIOR day's snapshot for the same ticker. This is a pure mechanical
diff -- no AI, no estimation -- so it never fabricates a trend; if there's
no prior snapshot yet (first time this ticker's been queried, or it's the
first call of the day), `what_changed` honestly reports
`{"available": False}` rather than inventing a baseline.

2026-08-30 (AJ: "起 Phase 2 3 一次過"): added Phase 2 and Phase 3 as two
more sub-sections, same zero-fabrication posture as above:
  - `business_relationship_mentions` (Phase 2, services/
    sec_business_text_service.py): literal sentence excerpts from the
    issuer's own 10-K naming a competitor/supplier/customer. This
    codebase's first raw-prose-document fetch from SEC EDGAR (every
    other SEC module here only ever touches structured JSON APIs). Each
    mention is a real quoted excerpt with a link back to the source
    filing -- never a cleaned-up/inferred "these are the competitors"
    list.
  - `event_impact` (Phase 3, services/event_impact_service.py): what the
    real stock price actually did after each of the ticker's most recent
    tracked Form 4 / 13D-13G events, computed live from real historical
    closes. Deliberately NOT the "average historical reaction" style
    feature this codebase already tried and explicitly rejected once
    (see engines/event_engine.py's docstring) -- this is a single real
    past outcome per event, not a statistic, and never implies
    causation or prediction.
Both sub-calls are wrapped in try/except: a Phase 2 or Phase 3 failure
degrades that section to {"available": False, ...} without breaking the
Phase 1 response that was already live in production.

2026-08-30 (Phase 4, AJ picked "cross-ticker fund overlap" from a 3-option
next-feature menu): added `smart_money_crossholdings` (services/
sec_ownership_service.py's get_smart_money_crossholdings()) -- for each
of our tracked concentrated managers (Berkshire/Pershing Square/Scion)
that holds this ticker, what ELSE (by real reported 13F value) that same
manager holds. Zero new data source: every row was already sitting in
sec_13f_holdings from Phase 1's ownership collector, just never queried
outside the single requested ticker's slice until now. Same
zero-fabrication posture: literal filing rows, real issuer names (no
CUSIP->ticker resolution exists yet, so no guessed tickers), never a
ranking or "smart money score".
"""
import os
import sqlite3
from datetime import datetime, timezone, date
from typing import Dict, Optional

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "xfinlab.db")

ATTRIBUTION = (
    "Combines SEC EDGAR Form 13F, 13D/13G, and Form 4 filings (sec.gov) with "
    "CFTC Commitments of Traders data (cftc.gov) already collected by XFINLAB's "
    "Data Factory. Public regulatory/market data, not investment advice."
)


def _get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_table():
    conn = _get_db()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS company_network_snapshots (
            ticker TEXT NOT NULL,
            snapshot_date TEXT NOT NULL,
            tracked_institutional_holders INTEGER,
            conviction_score REAL,
            recent_activist_filings_count INTEGER,
            insider_net_shares INTEGER,
            insider_net_value_usd REAL,
            commodity_net_noncomm INTEGER,
            created_at TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (ticker, snapshot_date)
        )
        """
    )
    conn.commit()
    conn.close()


_init_table()


def _save_snapshot_and_diff(ticker: str, summary: dict) -> dict:
    """Upserts today's snapshot for `ticker`, then diffs against the most
    recent snapshot strictly before today. Returns the `what_changed`
    block -- never raises (a snapshot-store failure must not break the
    main company-network response)."""
    today = date.today().isoformat()
    try:
        conn = _get_db()
        prior = conn.execute(
            """
            SELECT * FROM company_network_snapshots
            WHERE ticker = ? AND snapshot_date < ?
            ORDER BY snapshot_date DESC LIMIT 1
            """,
            (ticker, today),
        ).fetchone()

        conn.execute(
            """
            INSERT INTO company_network_snapshots
                (ticker, snapshot_date, tracked_institutional_holders, conviction_score,
                 recent_activist_filings_count, insider_net_shares, insider_net_value_usd,
                 commodity_net_noncomm)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ticker, snapshot_date) DO UPDATE SET
                tracked_institutional_holders=excluded.tracked_institutional_holders,
                conviction_score=excluded.conviction_score,
                recent_activist_filings_count=excluded.recent_activist_filings_count,
                insider_net_shares=excluded.insider_net_shares,
                insider_net_value_usd=excluded.insider_net_value_usd,
                commodity_net_noncomm=excluded.commodity_net_noncomm
            """,
            (
                ticker, today,
                summary.get("tracked_institutional_holders"),
                summary.get("conviction_score"),
                summary.get("recent_activist_filings_count"),
                summary.get("insider_net_shares"),
                summary.get("insider_net_value_usd"),
                summary.get("commodity_net_noncomm"),
            ),
        )
        conn.commit()
        conn.close()
    except Exception:
        return {"available": False, "message": "Snapshot unavailable this run."}

    if not prior:
        return {
            "available": False,
            "message": "No prior snapshot for this ticker yet -- check back tomorrow for a day-over-day diff.",
        }

    def _delta(key):
        new_v = summary.get(key)
        old_v = prior[key] if key in prior.keys() else None
        if new_v is None or old_v is None:
            return None
        try:
            d = new_v - old_v
            return round(d, 2) if isinstance(d, float) else d
        except TypeError:
            return None

    return {
        "available": True,
        "compared_to_date": prior["snapshot_date"],
        "tracked_institutional_holders_delta": _delta("tracked_institutional_holders"),
        "conviction_score_delta": _delta("conviction_score"),
        "recent_activist_filings_count_delta": _delta("recent_activist_filings_count"),
        "insider_net_shares_delta": _delta("insider_net_shares"),
        "insider_net_value_usd_delta": _delta("insider_net_value_usd"),
        "commodity_net_noncomm_delta": _delta("commodity_net_noncomm"),
    }


def get_company_network(ticker: str) -> Dict:
    """Returns:
        {"available": True, "ticker": "AAPL", "as_of": "...", "attribution": "...",
         "institutional_ownership": {...from sec_ownership_service.get_ownership_summary...},
         "conviction_score": {...from sec_ownership_service.get_conviction_score...},
         "activist_filings": {...from sec_13d_13g_service.search_recent_filings...},
         "insider_trading": {...from sec_form4_service.get_recent_insider_transactions...},
         "commodity_exposure": {...from cftc_cot_service.get_cot_for_ticker...} or None,
         "network_summary": {...pure pass-through counts/sums, see module docstring...},
         "what_changed": {...day-over-day diff, or {"available": False} if no prior snapshot...},
         "business_relationship_mentions": {...Phase 2, from sec_business_text_service...},
         "event_impact": {...Phase 3, from event_impact_service...},
         "smart_money_crossholdings": {...Phase 4, from sec_ownership_service...}}

    Always `available: True` at the top level (this endpoint never 503s) --
    each sub-section carries its own honest `available` flag independently,
    matching the rest of this API's convention: a ticker with zero tracked
    institutional holders and no COT linkage still returns a valid response,
    just with those sections showing `available: False`, never a fabricated
    reading."""
    ticker = (ticker or "").upper().strip()
    if not ticker:
        return {"available": False, "message": "ticker is required"}

    from services.sec_ownership_service import get_ownership_summary, get_conviction_score
    from services.sec_13d_13g_service import search_recent_filings
    from services.sec_form4_service import get_recent_insider_transactions
    from services.cftc_cot_service import get_cot_for_ticker

    ownership = get_ownership_summary(ticker)
    conviction = get_conviction_score(ticker)
    activist = search_recent_filings(ticker)
    insider = get_recent_insider_transactions(ticker)
    cot = get_cot_for_ticker(ticker)

    holders = ownership.get("holders") or [] if ownership.get("available") else []
    top_holder = None
    if holders:
        top = max(holders, key=lambda h: (h.get("value_usd") or 0))
        top_holder = {"filer_name": top.get("filer_name"), "value_usd": top.get("value_usd")}

    activist_filings_sorted = []
    if activist.get("available"):
        activist_filings_sorted = sorted(
            activist.get("filings") or [], key=lambda f: f.get("file_date") or "", reverse=True
        )
    most_recent_activist_filer = activist_filings_sorted[0]["filer_display_name"] if activist_filings_sorted else None

    insider_summary = insider.get("summary") if insider.get("available") else None

    network_summary = {
        "tracked_institutional_holders": len(holders) if ownership.get("available") else None,
        "top_holder": top_holder,
        "conviction_score": conviction.get("score") if conviction.get("available") else None,
        "recent_activist_filings_count": len(activist_filings_sorted) if activist.get("available") else 0,
        "most_recent_activist_filer": most_recent_activist_filer,
        "insider_net_shares": insider_summary.get("net_shares") if insider_summary else None,
        "insider_net_value_usd": insider_summary.get("net_value_usd") if insider_summary else None,
        "insider_buy_sell_count": (
            {"buy": insider_summary.get("buy_count"), "sell": insider_summary.get("sell_count")}
            if insider_summary else None
        ),
        "commodity_linked": bool(cot),
        "commodity_contract": cot.get("label") if cot else None,
        "commodity_net_noncomm": cot.get("net_noncomm") if cot else None,
    }

    what_changed = _save_snapshot_and_diff(ticker, network_summary)

    try:
        from services.sec_business_text_service import get_business_relationship_mentions
        business_relationship_mentions = get_business_relationship_mentions(ticker)
    except Exception:
        business_relationship_mentions = {"available": False, "message": "Business relationship extraction unavailable this run."}

    try:
        from services.event_impact_service import get_event_impact
        event_impact = get_event_impact(ticker)
    except Exception:
        event_impact = {"available": False, "message": "Event impact lookup unavailable this run."}

    try:
        from services.sec_ownership_service import get_smart_money_crossholdings
        smart_money_crossholdings = get_smart_money_crossholdings(ticker)
    except Exception:
        smart_money_crossholdings = {"available": False, "message": "Smart money crossholdings unavailable this run."}

    return {
        "available": True,
        "ticker": ticker,
        "as_of": datetime.now(timezone.utc).isoformat(),
        "attribution": ATTRIBUTION,
        "institutional_ownership": ownership,
        "conviction_score": conviction,
        "activist_filings": activist,
        "insider_trading": insider,
        "commodity_exposure": cot,
        "network_summary": network_summary,
        "what_changed": what_changed,
        "business_relationship_mentions": business_relationship_mentions,
        "event_impact": event_impact,
        "smart_money_crossholdings": smart_money_crossholdings,
    }
