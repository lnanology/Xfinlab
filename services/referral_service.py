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

# 2026-07-27 product decision ("推薦人介紹新用戶註冊並年付PRO PLAN，推薦人
# 馬上升上PRO用1年，介紹5個新人升至年費的PRO，推薦人升至PRO＋"): a SEPARATE,
# much bigger reward tier layered on top of the points-based one above --
# gated on the new user actually becoming a real ANNUAL Pro subscriber, not
# just signing up. Since the site has no live payment processor yet
# (pricing.html still shows "即將開放付款"), the trigger for "this user
# really paid" is ReferralService.mark_annual_pro_payment(), called from a
# new admin-only endpoint until a real Stripe/PayPal webhook exists to call
# it instead -- the reward logic itself doesn't care which one calls it.
#   - 1st..4th qualifying conversion: referrer is granted (or has extended,
#     see points_service.grant_temp_upgrade's stacking behavior) a real Pro
#     tier for 1 year, immediately.
#   - 5th and every subsequent qualifying conversion: referrer's grant
#     becomes Pro+ instead of Pro, same 1-year-per-conversion stacking.
# This is layered via the existing temp_upgrades mechanic (same table the
# points system's Basic boost uses), NOT by overwriting users.plan, so it
# auto-expires on its own and never clobbers whatever real plan the
# referrer separately has/earns.
REFERRAL_PRO_GRANT_DAYS = 365
REFERRAL_PROPLUS_THRESHOLD = 5

# Growth OS Phase 6 (2026-08-04): the 5 numbers above were previously
# hardcoded module constants -- fine while there was one person deciding
# the numbers, but the user's own Phase 6 brief asks for "toggle reward
# amounts" from the admin panel without a redeploy. Rather than a
# boolean feature_flags row (that table is specifically for on/off
# switches -- see api/admin.py's _DEFAULT_FLAGS docstring), this is a
# small parallel key/value table for *numeric* config, read through
# get_config() below. The module constants above remain as the seeded
# defaults and as a readable fallback if the table/row is ever missing
# (e.g. a fresh DB before init_referral_config_table() has run) -- every
# read site is a get_config(key, MODULE_CONSTANT) call, never a bare
# table read that could silently return None.
_REFERRAL_CONFIG_DEFAULTS = {
    "referrer_base_bonus": REFERRER_BASE_BONUS,
    "new_user_welcome_bonus": NEW_USER_WELCOME_BONUS,
    "referrer_quick_action_bonus": REFERRER_QUICK_ACTION_BONUS,
    "referral_pro_grant_days": REFERRAL_PRO_GRANT_DAYS,
    "referral_proplus_threshold": REFERRAL_PROPLUS_THRESHOLD,
}


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_referral_config_table():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS referral_config (
            key TEXT PRIMARY KEY,
            value INTEGER NOT NULL,
            updated_at TEXT DEFAULT (datetime('now'))
        )
    """)
    existing = {r["key"] for r in conn.execute("SELECT key FROM referral_config").fetchall()}
    for key, default_value in _REFERRAL_CONFIG_DEFAULTS.items():
        if key not in existing:
            conn.execute(
                "INSERT INTO referral_config (key, value) VALUES (?, ?)",
                (key, default_value),
            )
    conn.commit()
    conn.close()


init_referral_config_table()


def get_config(key: str) -> int:
    """Read one referral reward number, falling back to the module-level
    default (never None) if the table/row doesn't exist yet -- e.g. a
    fresh DB where this module was imported before
    init_referral_config_table() finished, or a key that predates a
    given deploy."""
    default = _REFERRAL_CONFIG_DEFAULTS.get(key)
    conn = get_db()
    try:
        row = conn.execute("SELECT value FROM referral_config WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default
    except Exception:
        return default
    finally:
        conn.close()


def get_all_config() -> dict:
    return {key: get_config(key) for key in _REFERRAL_CONFIG_DEFAULTS}


def set_config(key: str, value: int) -> dict:
    """Admin-only write path (see api/admin.py's
    POST /admin/referral/config/{key}) -- validates the key against the
    known whitelist so this can't be used to inject an arbitrary new
    row."""
    if key not in _REFERRAL_CONFIG_DEFAULTS:
        return {"success": False, "message": f"Unknown config key: {key}"}
    conn = get_db()
    conn.execute(
        "INSERT INTO referral_config (key, value, updated_at) VALUES (?, ?, datetime('now')) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
        (key, value),
    )
    conn.commit()
    conn.close()
    return {"success": True, "key": key, "value": value}


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
    # 2026-07-27 annual-Pro referral reward: tracks which referred signups
    # went on to actually pay for annual Pro, separately from the plain
    # signup already recorded above -- same guarded-ALTER pattern used
    # elsewhere in this codebase (e.g. backend/auth/auth.py's risk_flagged)
    # so re-running this on a DB that already has the columns is a no-op.
    try:
        conn.execute("ALTER TABLE referral_uses ADD COLUMN converted_paid_pro INTEGER DEFAULT 0")
    except Exception:
        pass
    try:
        conn.execute("ALTER TABLE referral_uses ADD COLUMN converted_at TEXT DEFAULT NULL")
    except Exception:
        pass
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

        # Growth OS Phase 6: read the live admin-configurable amounts
        # (get_config() falls back to the module constants above if the
        # referral_config table/row is missing) rather than the bare
        # constants directly, so an admin toggle takes effect on the very
        # next referral with no redeploy.
        base_bonus = get_config("referrer_base_bonus")
        quick_bonus = get_config("referrer_quick_action_bonus")
        welcome_bonus = get_config("new_user_welcome_bonus")

        referrer_bonus = base_bonus + (quick_bonus if quick_action else 0)
        add_bonus_points(referrer_id, referrer_bonus)
        add_bonus_points(new_user_id, welcome_bonus)

        return {
            "success": True,
            "message": "Referral applied",
            "referrer_points": referrer_bonus,
            "referrer_quick_action_bonus": quick_action,
            "new_user_points": welcome_bonus,
        }

    @staticmethod
    def mark_paid_conversion(new_user_id: int) -> dict:
        """2026-07-27: called once a referred user is confirmed to have
        actually paid for an ANNUAL Pro subscription (currently only
        reachable via ReferralService.mark_annual_pro_payment() below,
        since there's no live payment processor yet -- see
        REFERRAL_PRO_GRANT_DAYS's docstring above). Idempotent per
        new_user_id: only the first call for a given referred user grants
        anything; a second call is a harmless no-op (returns
        already_converted=True) so an admin re-clicking the same action
        twice, or a future webhook retry, can never double-grant.

        Silently no-ops (success=False) if this user was never referred
        at all -- a direct signup with no ?ref= code simply has no row in
        referral_uses to convert, which is expected, not an error.
        """
        conn = get_db()

        use_row = conn.execute(
            "SELECT id, referral_code, converted_paid_pro FROM referral_uses WHERE new_user_id=?",
            (new_user_id,)
        ).fetchone()

        if not use_row:
            conn.close()
            return {"success": False, "message": "This user was not referred by anyone"}

        if use_row["converted_paid_pro"]:
            conn.close()
            return {"success": False, "message": "Already converted", "already_converted": True}

        referral = conn.execute(
            "SELECT user_id FROM referrals WHERE referral_code=?", (use_row["referral_code"],)
        ).fetchone()
        if not referral:
            conn.close()
            return {"success": False, "message": "Referral code no longer exists"}
        referrer_id = referral["user_id"]

        conn.execute(
            "UPDATE referral_uses SET converted_paid_pro=1, converted_at=datetime('now') WHERE id=?",
            (use_row["id"],)
        )
        conn.commit()

        paid_conversions = conn.execute(
            """SELECT COUNT(*) as c FROM referral_uses
               WHERE referral_code=? AND converted_paid_pro=1""",
            (use_row["referral_code"],)
        ).fetchone()["c"]
        conn.close()

        tier = "proplus" if paid_conversions >= get_config("referral_proplus_threshold") else "pro"

        from services.points_service import grant_temp_upgrade
        expires_at = grant_temp_upgrade(referrer_id, tier, get_config("referral_pro_grant_days"))

        return {
            "success": True,
            "referrer_id": referrer_id,
            "reward_tier": tier,
            "reward_expires_at": expires_at,
            "paid_conversions": paid_conversions,
        }

    @staticmethod
    def mark_annual_pro_payment(user_id: int) -> dict:
        """2026-07-27: the current, temporary trigger point for "this user
        really paid for an annual Pro subscription" -- there is no live
        Stripe/PayPal integration yet, so this is admin-only (see
        POST /api/admin/users/{user_id}/mark-annual-pro) until a real
        payment webhook exists to call the exact same function instead.

        Sets the PAYER's own real plan + a real 1-year expiry (so their
        account genuinely reads as Pro, and services/quota_middleware.py's
        resolve_real_plan() will demote them back to free automatically
        once the year is up -- no separate cron/cleanup job needed).
        Then, if they were referred, triggers the referrer's reward via
        mark_paid_conversion() above.
        """
        conn = get_db()
        now = datetime.datetime.utcnow()
        expires_at = (now + datetime.timedelta(days=REFERRAL_PRO_GRANT_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
        conn.execute(
            "UPDATE users SET plan='pro', plan_expires_at=? WHERE id=?",
            (expires_at, user_id)
        )
        conn.commit()
        conn.close()

        referral_result = ReferralService.mark_paid_conversion(user_id)

        return {
            "user_id": user_id,
            "plan": "pro",
            "plan_expires_at": expires_at,
            "referral_reward": referral_result,
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

    @staticmethod
    def get_admin_dashboard(top_n: int = 20) -> dict:
        """Growth OS Phase 6 (2026-08-04) -- admin-facing referral stats
        dashboard (GET /admin/referral/stats). Read-only aggregate over
        the same referrals/referral_uses tables the user-facing
        get_stats()/get_global_stats() already use -- no new tables, no
        new write paths, just a devrel-style rollup for the admin panel."""
        conn = get_db()
        try:
            total_codes = conn.execute("SELECT COUNT(*) as c FROM referrals").fetchone()["c"]
            total_uses = conn.execute("SELECT COUNT(*) as c FROM referral_uses").fetchone()["c"]
            total_paid = conn.execute(
                "SELECT COUNT(*) as c FROM referral_uses WHERE converted_paid_pro=1"
            ).fetchone()["c"]

            top_rows = conn.execute(
                """
                SELECT r.referral_code, r.referred_count, r.created_at, u.email
                FROM referrals r
                LEFT JOIN users u ON u.id = r.user_id
                WHERE r.referred_count > 0
                ORDER BY r.referred_count DESC
                LIMIT ?
                """,
                (top_n,),
            ).fetchall()
            top_referrers = [
                {
                    "email": r["email"],
                    "referral_code": r["referral_code"],
                    "referred_count": r["referred_count"],
                    "created_at": r["created_at"],
                }
                for r in top_rows
            ]
        except Exception:
            total_codes = total_uses = total_paid = 0
            top_referrers = []
        finally:
            conn.close()

        return {
            "overview": {
                "total_codes_generated": total_codes,
                "total_successful_referrals": total_uses,
                "total_paid_conversions": total_paid,
            },
            "top_referrers": top_referrers,
            "config": get_all_config(),
        }
