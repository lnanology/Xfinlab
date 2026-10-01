"""
Research Memory / Hypothesis API -- 2026-10-01 (AJ: "找出未做的賺錢路線,
開發更新穎賺錢機會" follow-up to the 2026-09-30 monetization gap-analysis
session that shipped /v1/impact and /v1/evidence-scorecard). Of the ~20
directions discussed, this is the one genuinely missing, genuinely
buildable, genuinely differentiated layer that survived cross-checking
against what api/intelligence.py already ships -- Event/Impact (relationship_
graph_service.py), Evidence (evidence_scorecard_service.py), Reproducibility
(point-in-time fundamentals, sec_xbrl_service.get_company_facts_as_of),
Regime (regime_router_service.py), and per-ticker day-over-day diffs
(company_network_service.py's what_changed) were all already live before
this session started.

What's new here: most financial AI tools answer one question in isolation.
This stores the QUESTION itself as a persistent, versioned object a
developer's Agent can come back to -- a hypothesis about an entity, the
evidence for and against it, and a confidence score that updates over
time with a full audit trail of every prior version. Re-running the same
research six months later doesn't start from zero; it starts from "here's
what we believed last time, and why."

Scoped per API key (not public/shared) -- same ownership convention as
webhook_service.py's intelligence_webhooks table (api_key stored as the
plaintext header value, matched on every read/write, never looked up by
ID alone). A hypothesis belongs to whoever created it; there's no
cross-tenant read path.

Confidence is a plain 0.0-1.0 float the CALLER sets and updates --
this module does no NLP/sentiment scoring of its own. Evidence and
counter_evidence are freeform caller-supplied text + an optional source
URL, not auto-extracted from any XFINLAB data source (that composition
is left to the caller, who already has /v1/evidence-scorecard, /v1/events,
/v1/impact etc. available to inform what they write here).
"""
import os
import sqlite3
import time
from typing import Dict, List, Optional

_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "xfinlab.db")

_MAX_HYPOTHESES_PER_KEY = 500  # generous but bounded, same posture as webhook_service.py's per-key cap
_MAX_EVIDENCE_PER_HYPOTHESIS = 100
_VALID_STATUSES = {"active", "confirmed", "invalidated"}
_VALID_EVIDENCE_KINDS = {"evidence", "counter_evidence"}


def _get_db():
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_tables():
    conn = _get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS research_hypotheses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            api_key TEXT NOT NULL,
            ticker TEXT NOT NULL,
            statement TEXT NOT NULL,
            confidence REAL,
            status TEXT NOT NULL DEFAULT 'active',
            version INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS research_hypothesis_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            hypothesis_id INTEGER NOT NULL,
            version INTEGER NOT NULL,
            statement TEXT NOT NULL,
            confidence REAL,
            status TEXT NOT NULL,
            snapshot_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS research_hypothesis_evidence (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            hypothesis_id INTEGER NOT NULL,
            kind TEXT NOT NULL,
            text TEXT NOT NULL,
            source TEXT,
            added_at TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_research_hyp_key ON research_hypotheses(api_key)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_research_hyp_ticker ON research_hypotheses(ticker)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_research_ev_hyp ON research_hypothesis_evidence(hypothesis_id)")
    conn.commit()
    conn.close()


_init_tables()


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _row_to_hypothesis(row: sqlite3.Row) -> Dict:
    return {
        "id": row["id"],
        "ticker": row["ticker"],
        "statement": row["statement"],
        "confidence": row["confidence"],
        "status": row["status"],
        "version": row["version"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def create_hypothesis(api_key: str, ticker: str, statement: str, confidence: Optional[float] = None) -> Dict:
    conn = _get_db()
    count = conn.execute(
        "SELECT COUNT(*) AS n FROM research_hypotheses WHERE api_key=?", (api_key,)
    ).fetchone()["n"]
    if count >= _MAX_HYPOTHESES_PER_KEY:
        conn.close()
        return {"error": f"Hypothesis limit reached ({_MAX_HYPOTHESES_PER_KEY} per key) -- invalidate or delete old ones first"}

    now = _now()
    cur = conn.execute(
        "INSERT INTO research_hypotheses (api_key, ticker, statement, confidence, status, version, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, 'active', 1, ?, ?)",
        (api_key, ticker.upper().strip(), statement.strip(), confidence, now, now),
    )
    hyp_id = cur.lastrowid
    conn.execute(
        "INSERT INTO research_hypothesis_versions (hypothesis_id, version, statement, confidence, status, snapshot_at) "
        "VALUES (?, 1, ?, ?, 'active', ?)",
        (hyp_id, statement.strip(), confidence, now),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM research_hypotheses WHERE id=?", (hyp_id,)).fetchone()
    conn.close()
    return _row_to_hypothesis(row)


def list_hypotheses(api_key: str, ticker: Optional[str] = None, status: Optional[str] = None, limit: int = 50) -> List[Dict]:
    conn = _get_db()
    query = "SELECT * FROM research_hypotheses WHERE api_key=?"
    params: list = [api_key]
    if ticker:
        query += " AND ticker=?"
        params.append(ticker.upper().strip())
    if status:
        query += " AND status=?"
        params.append(status)
    query += " ORDER BY updated_at DESC LIMIT ?"
    params.append(max(1, min(limit, 200)))
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [_row_to_hypothesis(r) for r in rows]


def get_hypothesis(api_key: str, hypothesis_id: int) -> Optional[Dict]:
    conn = _get_db()
    row = conn.execute(
        "SELECT * FROM research_hypotheses WHERE id=? AND api_key=?", (hypothesis_id, api_key)
    ).fetchone()
    if not row:
        conn.close()
        return None

    result = _row_to_hypothesis(row)

    evidence_rows = conn.execute(
        "SELECT kind, text, source, added_at FROM research_hypothesis_evidence "
        "WHERE hypothesis_id=? ORDER BY added_at ASC",
        (hypothesis_id,),
    ).fetchall()
    result["evidence"] = [dict(r) for r in evidence_rows if r["kind"] == "evidence"]
    result["counter_evidence"] = [dict(r) for r in evidence_rows if r["kind"] == "counter_evidence"]

    version_rows = conn.execute(
        "SELECT version, statement, confidence, status, snapshot_at FROM research_hypothesis_versions "
        "WHERE hypothesis_id=? ORDER BY version ASC",
        (hypothesis_id,),
    ).fetchall()
    result["version_history"] = [dict(r) for r in version_rows]

    conn.close()
    return result


def update_hypothesis(
    api_key: str,
    hypothesis_id: int,
    statement: Optional[str] = None,
    confidence: Optional[float] = None,
    status: Optional[str] = None,
) -> Optional[Dict]:
    """Any change bumps `version` and appends a snapshot to
    research_hypothesis_versions -- the "git diff for financial research"
    piece. A caller who only wants to tweak confidence (not the statement)
    can omit `statement`; the prior value is carried forward into the new
    version row, not blanked."""
    if status is not None and status not in _VALID_STATUSES:
        return {"error": f"status must be one of {sorted(_VALID_STATUSES)}"}

    conn = _get_db()
    row = conn.execute(
        "SELECT * FROM research_hypotheses WHERE id=? AND api_key=?", (hypothesis_id, api_key)
    ).fetchone()
    if not row:
        conn.close()
        return None

    new_statement = statement.strip() if statement is not None else row["statement"]
    new_confidence = confidence if confidence is not None else row["confidence"]
    new_status = status if status is not None else row["status"]
    new_version = row["version"] + 1
    now = _now()

    conn.execute(
        "UPDATE research_hypotheses SET statement=?, confidence=?, status=?, version=?, updated_at=? WHERE id=?",
        (new_statement, new_confidence, new_status, new_version, now, hypothesis_id),
    )
    conn.execute(
        "INSERT INTO research_hypothesis_versions (hypothesis_id, version, statement, confidence, status, snapshot_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (hypothesis_id, new_version, new_statement, new_confidence, new_status, now),
    )
    conn.commit()
    updated_row = conn.execute("SELECT * FROM research_hypotheses WHERE id=?", (hypothesis_id,)).fetchone()
    conn.close()
    return _row_to_hypothesis(updated_row)


def add_evidence(api_key: str, hypothesis_id: int, kind: str, text: str, source: Optional[str] = None) -> Dict:
    if kind not in _VALID_EVIDENCE_KINDS:
        return {"error": f"kind must be one of {sorted(_VALID_EVIDENCE_KINDS)}"}

    conn = _get_db()
    owner_row = conn.execute(
        "SELECT id FROM research_hypotheses WHERE id=? AND api_key=?", (hypothesis_id, api_key)
    ).fetchone()
    if not owner_row:
        conn.close()
        return {"error": "Hypothesis not found"}

    existing_count = conn.execute(
        "SELECT COUNT(*) AS n FROM research_hypothesis_evidence WHERE hypothesis_id=?", (hypothesis_id,)
    ).fetchone()["n"]
    if existing_count >= _MAX_EVIDENCE_PER_HYPOTHESIS:
        conn.close()
        return {"error": f"Evidence limit reached ({_MAX_EVIDENCE_PER_HYPOTHESIS} per hypothesis)"}

    now = _now()
    conn.execute(
        "INSERT INTO research_hypothesis_evidence (hypothesis_id, kind, text, source, added_at) VALUES (?, ?, ?, ?, ?)",
        (hypothesis_id, kind, text.strip(), source, now),
    )
    # touching updated_at (without bumping version -- adding evidence isn't
    # a conclusion change, just more support for/against the existing one)
    conn.execute("UPDATE research_hypotheses SET updated_at=? WHERE id=?", (now, hypothesis_id))
    conn.commit()
    conn.close()
    return {"added": True, "kind": kind, "added_at": now}
