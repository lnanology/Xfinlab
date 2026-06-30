import sqlite3
import os
from datetime import datetime

DB_PATH = "/Users/aj/Desktop/Xfinlab-main/xfinlab.db"

# Free plan limits
FREE_LIMITS = {
    "full_analysis": 10,
    "research": 3,
    "report": 1,
}

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_quota_table():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS quota_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            feature TEXT NOT NULL,
            date TEXT NOT NULL,
            count INTEGER DEFAULT 0,
            UNIQUE(user_id, feature, date)
        )
    """)
    conn.commit()
    conn.close()

init_quota_table()


class QuotaService:
    """XFINLAB Quota Service - Controls Free/Pro usage limits"""

    @staticmethod
    def check(user_id: int, plan: str, feature: str) -> dict:
        """
        Check if user can use a feature

        Args:
            user_id: User ID
            plan: free or pro
            feature: full_analysis / research / report

        Returns:
            Dict with allowed, used, limit
        """
        if plan == "pro":
            return {"allowed": True, "used": 0, "limit": -1, "plan": "pro"}

        limit = FREE_LIMITS.get(feature, 5)
        today = datetime.now().strftime("%Y-%m-%d")

        conn = get_db()
        row = conn.execute(
            "SELECT count FROM quota_usage WHERE user_id=? AND feature=? AND date=?",
            (user_id, feature, today)
        ).fetchone()
        conn.close()

        used = row["count"] if row else 0
        allowed = used < limit

        return {
            "allowed": allowed,
            "used": used,
            "limit": limit,
            "plan": "free",
            "remaining": max(0, limit - used)
        }

    @staticmethod
    def increment(user_id: int, feature: str):
        """Increment usage count for today"""
        today = datetime.now().strftime("%Y-%m-%d")
        conn = get_db()
        conn.execute("""
            INSERT INTO quota_usage (user_id, feature, date, count)
            VALUES (?, ?, ?, 1)
            ON CONFLICT(user_id, feature, date)
            DO UPDATE SET count = count + 1
        """, (user_id, feature, today))
        conn.commit()
        conn.close()

    @staticmethod
    def get_usage(user_id: int) -> dict:
        """Get all usage for today"""
        today = datetime.now().strftime("%Y-%m-%d")
        conn = get_db()
        rows = conn.execute(
            "SELECT feature, count FROM quota_usage WHERE user_id=? AND date=?",
            (user_id, today)
        ).fetchall()
        conn.close()

        usage = {feature: 0 for feature in FREE_LIMITS}
        for row in rows:
            usage[row["feature"]] = row["count"]

        return {
            "date": today,
            "usage": usage,
            "limits": FREE_LIMITS
        }
