import os
import sqlite3
import random
import string
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "xfinlab.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_referral_table():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS referrals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            referral_code TEXT UNIQUE NOT NULL,
            referred_count INTEGER DEFAULT 0,
            reward_days INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS referral_uses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referral_code TEXT NOT NULL,
            new_user_id INTEGER NOT NULL,
            used_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    conn.close()

init_referral_table()


class ReferralService:
    """XFINLAB Referral Service - Track and reward user referrals"""

    @staticmethod
    def generate_code(user_id: int) -> str:
        """Generate unique referral code for user"""
        conn = get_db()
        row = conn.execute(
            "SELECT referral_code FROM referrals WHERE user_id=?", (user_id,)
        ).fetchone()

        if row:
            conn.close()
            return row["referral_code"]

        # Generate unique code
        while True:
            code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
            existing = conn.execute(
                "SELECT id FROM referrals WHERE referral_code=?", (code,)
            ).fetchone()
            if not existing:
                break

        conn.execute(
            "INSERT INTO referrals (user_id, referral_code) VALUES (?, ?)",
            (user_id, code)
        )
        conn.commit()
        conn.close()
        return code

    @staticmethod
    def use_code(code: str, new_user_id: int) -> dict:
        """Record referral code usage and reward referrer"""
        conn = get_db()

        # Check code exists
        referral = conn.execute(
            "SELECT * FROM referrals WHERE referral_code=?", (code,)
        ).fetchone()

        if not referral:
            conn.close()
            return {"success": False, "message": "Invalid referral code"}

        # Check not self-referral
        if referral["user_id"] == new_user_id:
            conn.close()
            return {"success": False, "message": "Cannot use your own referral code"}

        # Check not already used by this user
        existing = conn.execute(
            "SELECT id FROM referral_uses WHERE referral_code=? AND new_user_id=?",
            (code, new_user_id)
        ).fetchone()

        if existing:
            conn.close()
            return {"success": False, "message": "Referral code already used"}

        # Record usage
        conn.execute(
            "INSERT INTO referral_uses (referral_code, new_user_id) VALUES (?, ?)",
            (code, new_user_id)
        )

        # Reward referrer: +7 days Pro
        conn.execute(
            "UPDATE referrals SET referred_count=referred_count+1, reward_days=reward_days+7 WHERE referral_code=?",
            (code,)
        )

        conn.commit()
        conn.close()

        return {
            "success": True,
            "message": "Referral applied! Referrer gets 7 days Pro",
            "reward_days": 7
        }

    @staticmethod
    def get_stats(user_id: int) -> dict:
        """Get referral stats for user"""
        conn = get_db()
        row = conn.execute(
            "SELECT * FROM referrals WHERE user_id=?", (user_id,)
        ).fetchone()
        conn.close()

        if not row:
            return {
                "referral_code": None,
                "referred_count": 0,
                "reward_days": 0
            }

        return {
            "referral_code": row["referral_code"],
            "referred_count": row["referred_count"],
            "reward_days": row["reward_days"],
            "referral_link": f"https://finlab-ai.vercel.app?ref={row['referral_code']}"
        }
