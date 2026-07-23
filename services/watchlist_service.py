import os
import sqlite3

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "xfinlab.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_watchlist_table():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS watchlist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            ticker TEXT NOT NULL,
            added_at TEXT DEFAULT (datetime('now')),
            UNIQUE(user_id, ticker)
        )
    """)
    conn.commit()
    conn.close()

init_watchlist_table()


class WatchlistService:
    """XFINLAB Watchlist Service - User favorite stocks"""

    @staticmethod
    def add(user_id: int, ticker: str) -> dict:
        conn = get_db()
        try:
            conn.execute(
                "INSERT INTO watchlist (user_id, ticker) VALUES (?, ?)",
                (user_id, ticker.upper())
            )
            conn.commit()
            return {"status": "ok", "message": f"{ticker} 已加入自選股"}
        except sqlite3.IntegrityError:
            return {"status": "ok", "message": f"{ticker} 已在自選股中"}
        finally:
            conn.close()

    @staticmethod
    def remove(user_id: int, ticker: str) -> dict:
        conn = get_db()
        conn.execute(
            "DELETE FROM watchlist WHERE user_id=? AND ticker=?",
            (user_id, ticker.upper())
        )
        conn.commit()
        conn.close()
        return {"status": "ok", "message": f"{ticker} 已移除"}

    @staticmethod
    def get_all(user_id: int) -> list:
        conn = get_db()
        rows = conn.execute(
            "SELECT ticker, added_at FROM watchlist WHERE user_id=? ORDER BY added_at DESC",
            (user_id,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
