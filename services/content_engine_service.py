"""
Social content draft generator -- 2026-10-02 (AJ: "快有效" growth
strategy discussion -- asked for a fast, professional path to attract
retail users via social, like FB/IG/X). The advice given: don't chase
20 viral mechanics at once with no content team; pick ONE content type
("why did it move") backed entirely by already-built XFINLAB engines
(relationship_graph_service's Impact Graph, evidence_scorecard_service's
multi-dimensional evidence tally, market_pulse's daily confluence
signals), automate the DRAFT only, and keep a human in the loop before
anything goes out publicly.

This module deliberately does NOT post to any social platform. Per this
product's standing safety rules, publishing public content requires
explicit per-action human approval -- an AI-authored financial post is
exactly the kind of thing that should never go out unreviewed (a wrong
number or a misleading framing here has real reputational/compliance
cost, unlike a typo in an internal admin tool). So the pipeline stops at
"draft, stored, reviewable" -- see api/admin.py's content-drafts
endpoints for the review/approve/reject flow AJ actually uses to decide
what gets copy-pasted out.

Candidate selection reuses api.market_pulse._compute_free_signals() --
the exact same daily-ranked confluence signal list video_engine_service.py
already uses to pick "today's most interesting tickers" for the admin
video engine. Zero new data source, zero new fetch shape.

Every draft is composed entirely from real, already-computed XFINLAB
outputs (confluence direction/confidence, evidence scorecard tally,
curated supplier/customer/competitor relationships) -- never AI-
generated prose about the ticker, and never a buy/sell recommendation.
The whole point (per the growth-strategy discussion) is to be the
anti-finfluencer: evidence and relationships, not hype.
"""
import json
import os
import sqlite3
import time
from typing import Dict, List, Optional

_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "xfinlab.db")

_DEFAULT_DRAFT_COUNT = 5
_MAX_DRAFT_COUNT = 10
_VALID_STATUSES = {"pending", "approved", "rejected"}


def _get_db():
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_table():
    conn = _get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS content_drafts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            short_text TEXT NOT NULL,
            long_text TEXT NOT NULL,
            evidence_url TEXT NOT NULL,
            signal_snapshot TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL,
            reviewed_at TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_content_drafts_status ON content_drafts(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_content_drafts_created ON content_drafts(created_at)")
    conn.commit()
    conn.close()


_init_table()


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _pick_candidate_tickers(n: int) -> List[Dict]:
    """Reuses the same daily-ranked signal list video_engine_service.py's
    default (no custom-tickers) path already consumes. Ranked by
    confluence_confidence_pct descending -- "today's most directionally
    confident real signals", the natural "why did THIS one move" set.
    Best-effort: returns [] if the signals cache can't be computed (e.g.
    market closed with no cached result yet) rather than raising."""
    try:
        from api.market_pulse import _compute_free_signals
        cache = _compute_free_signals()
        signals = cache.get("signals") or []
    except Exception:
        return []

    ranked = sorted(
        (s for s in signals if s.get("confluence_confidence_pct") is not None),
        key=lambda s: s["confluence_confidence_pct"],
        reverse=True,
    )
    return ranked[:n]


def _format_relationships(items: List, label: str) -> str:
    """`items` is either a list of plain ticker strings (known_suppliers/
    known_customers/known_competitors) or a list of {ticker, name} dicts
    (sector_peers) -- relationship_graph_service.py's get_impact_analysis()
    returns both shapes from the same function, so this normalizes
    either to a flat list of ticker strings before joining."""
    if not items:
        return ""
    tickers = [i["ticker"] if isinstance(i, dict) else i for i in items]
    shown = tickers[:3]
    suffix = f" (+{len(tickers) - 3} more)" if len(tickers) > 3 else ""
    return f"{label}: {', '.join(shown)}{suffix}"


def build_why_it_moved_draft(ticker: str, signal: Optional[Dict] = None) -> Dict:
    """Composes one draft from three already-existing, real-data engines
    -- never fabricates a number or a relationship. Any sub-source
    failing just omits that part of the text (same best-effort posture
    as get_impact_analysis/get_evidence_scorecard themselves)."""
    ticker = ticker.upper().strip()

    if signal is None:
        candidates = _pick_candidate_tickers(50)
        signal = next((s for s in candidates if s.get("ticker") == ticker), None) or {}

    direction = signal.get("confluence_direction")
    confidence = signal.get("confluence_confidence_pct")
    label = signal.get("label") or ticker

    try:
        from services.evidence_scorecard_service import get_evidence_scorecard
        evidence = get_evidence_scorecard(ticker)
    except Exception:
        evidence = {}

    try:
        from services.relationship_graph_service import get_impact_analysis
        impact = get_impact_analysis(ticker)
    except Exception:
        impact = {}

    support = evidence.get("support_count")
    oppose = evidence.get("oppose_count")
    has_disagreement = evidence.get("has_disagreement")
    confluence_pct = evidence.get("confluence_pct")

    evidence_url = f"https://www.xfinlab.com/evidence-scorecard.html?ticker={ticker}"

    # --- short (X-length) draft ---
    direction_phrase = {
        "偏多": "a bullish", "偏空": "a bearish",
        "bullish": "a bullish", "bearish": "a bearish",
    }.get(direction, "a mixed")
    short_parts = [f"{label} ({ticker}) is showing {direction_phrase} signal today"]
    if confidence is not None:
        short_parts.append(f"({confidence}% confluence confidence)")
    if support is not None and oppose is not None:
        short_parts.append(f"-- {support} of 11 independent evidence sources agree, {oppose} disagree.")
    if has_disagreement:
        short_parts.append("Sources are split -- not a clean signal.")
    short_parts.append(f"Full evidence: {evidence_url}")
    short_text = " ".join(short_parts)

    # --- long (Reddit-style) draft ---
    long_lines = [f"**{label} ({ticker}) -- what the evidence actually shows**", ""]
    if direction is not None and confidence is not None:
        long_lines.append(f"Confluence signal: {direction_phrase} direction, {confidence}% confidence (real technical indicators, not an AI guess).")
    if support is not None and oppose is not None:
        long_lines.append(f"Evidence scorecard: {support} sources support, {oppose} oppose, {evidence.get('neutral_count', 0)} neutral, out of {evidence.get('dimensions_available', '?')} available.")
    if confluence_pct is not None:
        long_lines.append(f"Confluence among directional sources: {confluence_pct}%.")
    if has_disagreement:
        long_lines.append("Note: independent evidence sources disagree with each other on this one -- flagged, not averaged away.")

    rel_lines = []
    rel_lines.append(_format_relationships(impact.get("known_suppliers") or [], "Suppliers"))
    rel_lines.append(_format_relationships(impact.get("known_customers") or [], "Customers"))
    rel_lines.append(_format_relationships(impact.get("known_competitors") or [], "Competitors"))
    rel_lines.append(_format_relationships(impact.get("sector_peers") or [], "Sector peers"))
    rel_lines = [l for l in rel_lines if l]
    if rel_lines:
        long_lines.append("")
        long_lines.append("Who else this touches:")
        long_lines.extend(f"- {l}" for l in rel_lines)

    long_lines.append("")
    long_lines.append(f"Full evidence + impact graph: {evidence_url}")
    long_lines.append("")
    long_lines.append("(Not investment advice -- this is a research tool, not a buy/sell call.)")
    long_text = "\n".join(long_lines)

    return {
        "ticker": ticker,
        "short_text": short_text,
        "long_text": long_text,
        "evidence_url": evidence_url,
        "signal_snapshot": {
            "direction": direction,
            "confidence": confidence,
            "support_count": support,
            "oppose_count": oppose,
            "has_disagreement": has_disagreement,
        },
    }


def generate_daily_drafts(n: int = _DEFAULT_DRAFT_COUNT) -> List[Dict]:
    """Picks today's top-N confluence signals and generates a draft for
    each, storing them as `pending` for human review. Returns the stored
    rows (with their new ids). Safe to call more than once a day --
    there's no dedup against a prior run's drafts for the same ticker,
    by design: if AJ runs this twice (once for a quick preview, once for
    real), stale/unwanted drafts are just rejected in the review queue,
    same posture as any other admin-triggered generation in this
    codebase (e.g. video_engine's Generate Now)."""
    n = max(1, min(n, _MAX_DRAFT_COUNT))
    candidates = _pick_candidate_tickers(n)
    if not candidates:
        return []

    conn = _get_db()
    now = _now()
    stored = []
    for signal in candidates:
        ticker = signal.get("ticker")
        if not ticker:
            continue
        try:
            draft = build_why_it_moved_draft(ticker, signal)
        except Exception:
            continue
        cur = conn.execute(
            "INSERT INTO content_drafts (ticker, short_text, long_text, evidence_url, signal_snapshot, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, 'pending', ?)",
            (draft["ticker"], draft["short_text"], draft["long_text"], draft["evidence_url"],
             json.dumps(draft["signal_snapshot"]), now),
        )
        draft["id"] = cur.lastrowid
        draft["status"] = "pending"
        draft["created_at"] = now
        stored.append(draft)
    conn.commit()
    conn.close()
    return stored


def list_drafts(status: Optional[str] = None, limit: int = 50) -> List[Dict]:
    conn = _get_db()
    query = "SELECT * FROM content_drafts"
    params: list = []
    if status:
        query += " WHERE status=?"
        params.append(status)
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(max(1, min(limit, 200)))
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def set_draft_status(draft_id: int, status: str) -> Optional[Dict]:
    if status not in _VALID_STATUSES:
        return {"error": f"status must be one of {sorted(_VALID_STATUSES)}"}
    conn = _get_db()
    row = conn.execute("SELECT id FROM content_drafts WHERE id=?", (draft_id,)).fetchone()
    if not row:
        conn.close()
        return None
    now = _now()
    conn.execute("UPDATE content_drafts SET status=?, reviewed_at=? WHERE id=?", (status, now, draft_id))
    conn.commit()
    updated = conn.execute("SELECT * FROM content_drafts WHERE id=?", (draft_id,)).fetchone()
    conn.close()
    return dict(updated)
