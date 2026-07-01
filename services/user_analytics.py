import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "xfinlab.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_analytics_table():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS user_analytics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            session_id TEXT,
            event_type TEXT NOT NULL,
            event_data TEXT,
            page TEXT,
            ip TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    conn.close()

init_analytics_table()


class UserAnalytics:
    """XFINLAB User Analytics - Track user behavior"""

    @staticmethod
    def track(event_type: str, event_data: dict = None,
              user_id: int = None, session_id: str = None,
              page: str = None, ip: str = None):
        """
        Track a user event

        Event types:
            page_view       - User viewed a page
            search          - User searched a stock
            analysis_run    - User ran full analysis
            research_view   - User viewed AI research
            report_download - User downloaded PDF report
            share           - User shared content
            login           - User logged in
            register        - User registered
            upgrade_click   - User clicked upgrade
        """
        import json
        conn = get_db()
        conn.execute("""
            INSERT INTO user_analytics
            (user_id, session_id, event_type, event_data, page, ip)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            user_id,
            session_id,
            event_type,
            json.dumps(event_data) if event_data else None,
            page,
            ip
        ))
        conn.commit()
        conn.close()

    @staticmethod
    def get_stats() -> dict:
        """Get overall analytics stats"""
        conn = get_db()

        total_events = conn.execute("SELECT COUNT(*) as c FROM user_analytics").fetchone()["c"]
        today = datetime.now().strftime("%Y-%m-%d")

        today_events = conn.execute(
            "SELECT COUNT(*) as c FROM user_analytics WHERE created_at LIKE ?",
            (f"{today}%",)
        ).fetchone()["c"]

        top_searches = conn.execute("""
            SELECT event_data, COUNT(*) as c
            FROM user_analytics
            WHERE event_type = 'search'
            GROUP BY event_data
            ORDER BY c DESC
            LIMIT 10
        """).fetchall()

        event_counts = conn.execute("""
            SELECT event_type, COUNT(*) as c
            FROM user_analytics
            GROUP BY event_type
            ORDER BY c DESC
        """).fetchall()

        conn.close()

        return {
            "total_events": total_events,
            "today_events": today_events,
            "top_searches": [dict(r) for r in top_searches],
            "event_counts": [dict(r) for r in event_counts]
        }
