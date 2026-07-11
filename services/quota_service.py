import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "xfinlab.db")

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
    # 2026-07-11 fix: api/onboarding.py 完成 3 步後承諾送「額外 3 次分析」，
    # 但原本個implementation直接insert入quota_usage、用feature=
    # 'full_analysis_bonus'（同真正check()用嘅'full_analysis'唔同key），
    # 加上QuotaService.check()從來冇讀過呢個bucket，結果個bonus承諾咗
    # 但用戶實際上從未真正收到過。用一個獨立table正式將bonus計入當日limit。
    conn.execute("""
        CREATE TABLE IF NOT EXISTS quota_bonus (
            user_id INTEGER NOT NULL,
            feature TEXT NOT NULL,
            date TEXT NOT NULL,
            bonus INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, feature, date)
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
        # pricing.html promises "Unlimited AI analyses/research/PDF
        # reports" starting from the Starter tier, not just Pro -- Pro's
        # extra value-add over Starter is portfolio tracking/API
        # access/priority processing, not higher quota. Payment isn't
        # wired up yet (pricing.html's handleUpgrade() is still a
        # "coming soon" stub), but this must be correct before it is,
        # otherwise a paying Starter customer would silently still be
        # capped at the free daily limits.
        if plan in ("pro", "starter"):
            return {"allowed": True, "used": 0, "limit": -1, "plan": plan}

        today = datetime.now().strftime("%Y-%m-%d")
        base_limit = FREE_LIMITS.get(feature, 5)

        conn = get_db()
        row = conn.execute(
            "SELECT count FROM quota_usage WHERE user_id=? AND feature=? AND date=?",
            (user_id, feature, today)
        ).fetchone()
        bonus_row = conn.execute(
            "SELECT bonus FROM quota_bonus WHERE user_id=? AND feature=? AND date=?",
            (user_id, feature, today)
        ).fetchone()
        conn.close()

        bonus = bonus_row["bonus"] if bonus_row else 0
        limit = base_limit + bonus
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
    def grant_bonus(user_id: int, feature: str, amount: int, date: str = None):
        """
        Add `amount` extra uses on top of the daily FREE_LIMITS for
        `feature`, for a specific day (defaults to today). Used by
        api/onboarding.py's completion reward. Additive -- calling this
        twice for the same user/feature/day accumulates rather than
        overwriting, so re-running an idempotent caller never loses a
        previously granted bonus.
        """
        target_date = date or datetime.now().strftime("%Y-%m-%d")
        conn = get_db()
        conn.execute("""
            INSERT INTO quota_bonus (user_id, feature, date, bonus)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id, feature, date)
            DO UPDATE SET bonus = bonus + excluded.bonus
        """, (user_id, feature, target_date, amount))
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
