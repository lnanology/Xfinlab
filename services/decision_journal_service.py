"""
Decision Journal Service -- Tier 2 layered-UX addition (2026-07-18).

Same raw-sqlite pattern as services/watchlist_service.py (a separate
table from the pre-existing, never-wired-up SQLAlchemy `DecisionJournal`
model in database/db.py -- that model has zero real usage anywhere in
the codebase, same "duplicate scaffold vs the thing actually in use"
pattern already documented for engines/ vs backend/engines/, not
something this pass tries to reconcile).

Lets a user save a snapshot of what an analysis showed them at decision
time (rating/confidence/entry-stop-target/note), and look it back up
later -- the whole point of a "have I actually been right" trail rather
than a page that's forgotten the moment you close the tab.
"""

import json
import os
import sqlite3

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "xfinlab.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_decision_journal_table():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS decision_journal_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            symbol TEXT NOT NULL,
            rating TEXT,
            confidence_pct REAL,
            entry_price REAL,
            stop_loss REAL,
            take_profit REAL,
            note TEXT,
            snapshot_json TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    conn.close()


init_decision_journal_table()


class DecisionJournalService:
    """XFINLAB Decision Journal -- save/list a user's own analysis decisions."""

    @staticmethod
    def add(user_id: int, symbol: str, entry: dict) -> dict:
        conn = get_db()
        try:
            conn.execute(
                """INSERT INTO decision_journal_entries
                   (user_id, symbol, rating, confidence_pct, entry_price,
                    stop_loss, take_profit, note, snapshot_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    user_id,
                    symbol.upper(),
                    entry.get("rating"),
                    entry.get("confidence_pct"),
                    entry.get("entry_price"),
                    entry.get("stop_loss"),
                    entry.get("take_profit"),
                    entry.get("note"),
                    json.dumps(entry.get("snapshot")) if entry.get("snapshot") else None,
                ),
            )
            conn.commit()
            return {"status": "ok", "message": f"{symbol} 已加入 Decision Journal"}
        finally:
            conn.close()

    @staticmethod
    def get_all(user_id: int) -> list:
        conn = get_db()
        try:
            rows = conn.execute(
                """SELECT id, symbol, rating, confidence_pct, entry_price,
                          stop_loss, take_profit, note, created_at
                   FROM decision_journal_entries
                   WHERE user_id=? ORDER BY created_at DESC""",
                (user_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    @staticmethod
    def remove(user_id: int, entry_id: int) -> dict:
        conn = get_db()
        try:
            conn.execute(
                "DELETE FROM decision_journal_entries WHERE user_id=? AND id=?",
                (user_id, entry_id),
            )
            conn.commit()
            return {"status": "ok", "message": "已刪除紀錄"}
        finally:
            conn.close()
