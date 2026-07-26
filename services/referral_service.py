import os
import sqlite3
import random
import string
import datetime

from services.points_service import add_bonus_points

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "xfinlab.db")

# 2026-07-26 product decision (referral reward redesign): dual-sided,
# instant reward instead of the old dead "+7 days Pro via a reward_days
# counter that never actually touched users.plan" mechanic below.
#   - Referrer: +50 points the moment their code is used by a real new
#     signup.
#   - New user: +30 points immediately as a "新手見面禮" welcome gift.
#   - Referrer quick-action bonus: an ADDITIONAL +50 (on top of the base
#     50, so +100 total) if the referrer's own account is <=2 days old at
#     the moment their referral lands -- rewards brand-new users who
#     share their link fast, on top of the standard reward every user
#     (new or veteran) always gets for any successful referral.
# All 3 numbers feed the shared 500-point/7-day-cycle mechanic in
# services/points_service.py, so a big referral push can push a free user
# over the temporary-Basic-upgrade threshold exactly like organic feature
# usage can.
REFERRER_BASE_BONUS = 50
NEW_USER_WELCOME_BONUS = 30
REFERRER_QUICK_ACTION_BONUS = 50
REFERRER_QUICK_ACTION_WINDOW_DAYS = 2
# 2026-07-26: progress-bar target shown in the referral UI ("已邀請X/5位
# 朋友") -- purely a UI milestone, does not cap how many referrals actually
# earn points (a 6th, 7th, etc. referral still pays out the same as any
# other; there's no numeric limit on the reward side here).
REFERRAL_PROGRESS_TARGET = 5


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
        """Record referral code usage and reward BOTH sides in points
        (see the REFERRER_BASE_BONUS/NEW_USER_WELCOME_BONUS/
        REFERRER_QUICK_ACTION_BONUS constants above). Called from
        backend/auth/auth.py's register() right after a new account is
        created -- failures here (bad code, self-referral, already used)
        are non-fatal to registration; the caller wraps this in a
        try/except and never blocks account creation over a referral
        problem.
        """
        conn = get_db()

        # Check code exists
        referral = conn.execute(
            "SELECT * FROM referrals WHERE referral_code=?", (code,)
        ).fetchone()

        if not referral:
            conn.close()
            return {"success": False, "message": "Invalid referral code"}

        referrer_id = referral["user_id"]

        # Check not self-referral
        if referrer_id == new_user_id:
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

        # Is the referrer themselves a brand-new user (joined <=2 days
        # ago)? Drives the "quick-action" bonus -- rewards new users who
        # share their link immediately instead of waiting.
        referrer_row = conn.execute(
            "SELECT created_at FROM users WHERE id=?", (referrer_id,)
        ).fetchone()
        quick_action = False
        if referrer_row and referrer_row["created_at"]:
            try:
                created_at = datetime.datetime.strptime(
                    referrer_row["created_at"], "%Y-%m-%d %H:%M:%S"
                )
                age_days = (datetime.datetime.utcnow() - created_at).days
                quick_action = age_days <= REFERRER_QUICK_ACTION_WINDOW_DAYS
            except (ValueError, TypeError):
                quick_action = False

        # Record usage
        conn.execute(
            "INSERT INTO referral_uses (referral_code, new_user_id) VALUES (?, ?)",
            (code, new_user_id)
        )
        conn.execute(
            "UPDATE referrals SET referred_count=referred_count+1 WHERE referral_code=?",
            (code,)
        )
        conn.commit()
        conn.close()

        referrer_bonus = REFERRER_BASE_BONUS + (REFERRER_QUICK_ACTION_BONUS if quick_action else 0)
        add_bonus_points(referrer_id, referrer_bonus)
        add_bonus_points(new_user_id, NEW_USER_WELCOME_BONUS)

        return {
            "success": True,
            "message": "Referral applied",
            "referrer_points": referrer_bonus,
            "referrer_quick_action_bonus": quick_action,
            "new_user_points": NEW_USER_WELCOME_BONUS,
        }

    @staticmethod
    def get_stats(user_id: int) -> dict:
        """Get referral stats for user. Auto-generates a code on first
        call (2026-07-26) so the referral UI can call this single
        endpoint and always get a usable link/code back, instead of
        needing a separate /referral/code call first just to bootstrap
        it."""
        conn = get_db()
        row = conn.execute(
            "SELECT * FROM referrals WHERE user_id=?", (user_id,)
        ).fetchone()
        conn.close()

        if not row:
            code = ReferralService.generate_code(user_id)
            return {
                "referral_code": code,
                "referred_count": 0,
                "target": REFERRAL_PROGRESS_TARGET,
                "referral_link": f"https://www.xfinlab.com/login.html?ref={code}",
            }

        return {
            "referral_code": row["referral_code"],
            "referred_count": row["referred_count"],
            "target": REFERRAL_PROGRESS_TARGET,
            "referral_link": f"https://www.xfinlab.com/login.html?ref={row['referral_code']}",
        }

    @staticmethod
    def get_global_stats() -> dict:
        """Site-wide social-proof number ("已有 XXX 人成功推薦") -- total
        successful referral uses across every user, not just this one."""
        conn = get_db()
        row = conn.execute("SELECT COUNT(*) as c FROM referral_uses").fetchone()
        conn.close()
        return {"total_successful_referrals": row["c"]}
