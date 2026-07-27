"""
Free-tier engagement points system.

Product design (2026-07-16, per explicit user instruction):
- Every time a logged-in FREE-plan user uses any AI-consuming "basic
  feature" (full_analysis/research/report -- the existing daily-count
  gated features -- plus ai_analysis/chat/stress_lab/company_compare/
  chart_analysis, which previously had NO free-tier limit at all), they
  earn 1 point.
- This REPLACES the old flat "5 analyses/day" style caps for these
  features -- a logged-in free user is never hard-blocked by this
  system; usage is always allowed, only counted.
- Points accumulate in a rolling 7-day cycle. If a user reaches 500
  points within 7 days of their current cycle starting, they earn a
  temporary upgrade to the Basic plan for the next 7 days (during which
  the REAL Basic-tier monthly token quota from token_quota_service.py
  applies, same as an actually-paying Basic subscriber), and their
  points cycle immediately resets to 0 so they start fresh.
- If 7 days pass without reaching 500, the cycle simply resets to 0
  with no reward and no penalty -- this is a rolling weekly allowance/
  gamification mechanic, not a hard quota.
- Only ever applies to users whose real plan (in the `users` table) is
  "free". Paying users on any tier don't participate in this system --
  they already have real token quotas.
"""

import sqlite3
import os
import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "xfinlab.db")

POINTS_TARGET = 500
CYCLE_DAYS = 7
REWARD_PLAN = "basic"

# 2026-07-27 referral-driven annual-Pro reward batch: `temp_upgrades` used to
# only ever be checked when a user's real plan was "free" (the points-cycle
# Basic boost). The referral reward (services/referral_service.py) needs the
# same "temporary plan on top of whatever the user really has, auto-expires,
# no DB write needed elsewhere" mechanic, but for a real Pro/Basic/etc payer
# too -- e.g. a Basic subscriber who earns a referral-driven comp'd Pro year
# should actually get Pro-level access for that year, not have it silently
# ignored because their real plan already isn't "free". PLAN_RANK is the
# ordering used to decide whether an active temp upgrade should win.
PLAN_RANK = {"free": 0, "basic": 1, "pro": 2, "proplus": 3, "professional": 4, "enterprise": 5}


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_points_tables():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS points_cycle (
            user_id INTEGER PRIMARY KEY,
            window_start TEXT NOT NULL,
            count INTEGER NOT NULL DEFAULT 0
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS temp_upgrades (
            user_id INTEGER PRIMARY KEY,
            plan TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            granted_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    conn.close()


init_points_tables()


def _now():
    return datetime.datetime.utcnow()


def _parse(ts):
    return datetime.datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")


def _fmt(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _get_cycle(conn, user_id):
    row = conn.execute(
        "SELECT window_start, count FROM points_cycle WHERE user_id=?", (user_id,)
    ).fetchone()
    return row


def _get_active_upgrade(conn, user_id):
    row = conn.execute(
        "SELECT plan, expires_at FROM temp_upgrades WHERE user_id=?", (user_id,)
    ).fetchone()
    if not row:
        return None
    if _parse(row["expires_at"]) <= _now():
        return None
    return {"plan": row["plan"], "expires_at": row["expires_at"]}


def get_effective_plan(user_id, base_plan):
    """Returns the plan that should actually be used for quota/gating
    decisions: base_plan, unless the user has an active temporary
    upgrade (points-cycle Basic boost, or a referral-driven Pro/Pro+
    grant -- see grant_temp_upgrade() below) that outranks it. Before
    2026-07-27 this only ever applied when base_plan == "free"; that
    behavior is preserved exactly (a "basic" temp upgrade still only
    ever beats "free"), this just also lets a higher-ranked temp grant
    (e.g. "pro"/"proplus") take effect for a user whose real plan is
    already something other than free."""
    conn = get_db()
    upgrade = _get_active_upgrade(conn, user_id)
    conn.close()
    if not upgrade:
        return base_plan
    if PLAN_RANK.get(upgrade["plan"], 0) > PLAN_RANK.get(base_plan, 0):
        return upgrade["plan"]
    return base_plan


def get_status(user_id):
    """Read-only status for display (points badge, account page). Never
    mutates state or grants anything -- only record_and_check() does."""
    conn = get_db()
    now = _now()
    cycle = _get_cycle(conn, user_id)
    upgrade = _get_active_upgrade(conn, user_id)
    conn.close()

    if not cycle:
        return {
            "points": 0, "target": POINTS_TARGET,
            "cycle_started": None, "cycle_ends": None,
            "temp_plan": upgrade["plan"] if upgrade else None,
            "temp_expires_at": upgrade["expires_at"] if upgrade else None,
        }

    window_start = _parse(cycle["window_start"])
    # A cycle that's aged past 7 days without being reset by a real
    # write is stale -- report it as already-reset (0 points) rather
    # than a misleadingly high number that record_and_check() would
    # reset on the next actual use anyway.
    if (now - window_start).days >= CYCLE_DAYS:
        points = 0
        cycle_ends = None
    else:
        points = cycle["count"]
        cycle_ends = _fmt(window_start + datetime.timedelta(days=CYCLE_DAYS))

    return {
        "points": points, "target": POINTS_TARGET,
        "cycle_started": cycle["window_start"], "cycle_ends": cycle_ends,
        "temp_plan": upgrade["plan"] if upgrade else None,
        "temp_expires_at": upgrade["expires_at"] if upgrade else None,
    }


def _add_points(user_id, amount):
    """Shared mutator behind both record_and_check() (always +1, per
    basic-feature use) and add_bonus_points() (2026-07-26: arbitrary
    amount, for referral rewards) -- both need the exact same rolling
    7-day-cycle-plus-500-target-grant logic, so it lives here once
    instead of being duplicated."""
    conn = get_db()
    now = _now()
    cycle = _get_cycle(conn, user_id)

    if not cycle:
        window_start = now
        count = 0
    else:
        window_start = _parse(cycle["window_start"])
        count = cycle["count"]
        if (now - window_start).days >= CYCLE_DAYS:
            # Cycle expired without hitting the target -- fresh start,
            # no reward, no penalty.
            window_start = now
            count = 0

    count += amount
    reward_granted = False

    if count >= POINTS_TARGET:
        expires_at = _fmt(now + datetime.timedelta(days=CYCLE_DAYS))
        conn.execute("""
            INSERT INTO temp_upgrades (user_id, plan, expires_at, granted_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                plan = excluded.plan, expires_at = excluded.expires_at, granted_at = excluded.granted_at
        """, (user_id, REWARD_PLAN, expires_at, _fmt(now)))
        # Reset immediately -- next cycle starts fresh. Note: any points
        # earned beyond the 500 threshold in this single addition (e.g. a
        # referral bonus that pushes 470 -> 520) are intentionally not
        # carried over into the new cycle -- same "reset to exactly 0"
        # behavior record_and_check() always had, just now also reachable
        # via a bonus instead of only ever by +1 increments.
        window_start = now
        count = 0
        reward_granted = True

    conn.execute("""
        INSERT INTO points_cycle (user_id, window_start, count)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            window_start = excluded.window_start, count = excluded.count
    """, (user_id, _fmt(window_start), count))
    conn.commit()
    conn.close()

    return {"points": count, "target": POINTS_TARGET, "reward_granted": reward_granted}


def record_and_check(user_id):
    """Call once per basic-feature use by a logged-in FREE-plan user
    (callers are responsible for only calling this when the user's real
    plan is "free" and they have no currently-active temp upgrade --
    see services/quota_middleware.py). Always allows the use; only
    tracks points and grants the reward when earned."""
    return _add_points(user_id, 1)


def add_bonus_points(user_id, amount):
    """2026-07-26 addition: credit a lump sum of points outside the
    normal +1-per-feature-use flow -- built for services/referral_service.py's
    referral rewards (+50 referrer / +30 new-user welcome gift / +50
    referrer "quick-action" bonus), but generic enough for any future
    one-off bonus. Shares record_and_check()'s exact same cycle-window
    and 500-point reward-granting behavior via _add_points() above, so a
    referral bonus can push a free user over the Basic-upgrade threshold
    exactly like organic feature usage can.
    """
    return _add_points(user_id, amount)


def grant_temp_upgrade(user_id: int, plan: str, days: int) -> str:
    """2026-07-27: generic grant/extend for the temp_upgrades mechanic --
    built for the referral annual-Pro reward (services/referral_service.py's
    mark_paid_conversion(), which calls this with plan="pro" or "proplus"
    and days=365 per qualifying referred conversion) but usable for any
    future "comp this user a plan tier for N days" case.

    If the user already has an active grant at the same or lower rank,
    this EXTENDS from its current expiry (stacks) rather than resetting
    the clock -- a referrer who earns a second 1-year Pro grant while
    their first year is still running ends up with ~2 years, not a reset
    1 year. If the new grant outranks or replaces an expired/absent one,
    it starts counting from now. Returns the resulting expires_at string.
    """
    conn = get_db()
    now = _now()
    existing = conn.execute(
        "SELECT plan, expires_at FROM temp_upgrades WHERE user_id=?", (user_id,)
    ).fetchone()

    base_from = now
    if existing:
        try:
            cur_expiry = _parse(existing["expires_at"])
            still_active = cur_expiry > now
            not_a_downgrade = PLAN_RANK.get(existing["plan"], 0) <= PLAN_RANK.get(plan, 0)
            if still_active and not_a_downgrade:
                base_from = cur_expiry
        except (ValueError, TypeError):
            pass

    expires_at = _fmt(base_from + datetime.timedelta(days=days))
    conn.execute("""
        INSERT INTO temp_upgrades (user_id, plan, expires_at, granted_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            plan = excluded.plan, expires_at = excluded.expires_at, granted_at = excluded.granted_at
    """, (user_id, plan, expires_at, _fmt(now)))
    conn.commit()
    conn.close()
    return expires_at
