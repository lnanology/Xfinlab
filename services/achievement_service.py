"""
Achievement / milestone badges -- 2026-09-27 (AJ: "起啦" after a research
pass on platform monetization psychology, deliberately scoped to the
POSITIVE half of that research only: streak/milestone badges tied to
genuine usage, never anything transaction-pressure or urgency-framed. See
services/quota_middleware.py's module comments for why -- 2026 is the
exact year several jurisdictions (Germany, June 2026; India, July 2026
if finalised) started explicitly banning "dark pattern" manipulative
design in financial-services apps, so this module is deliberately kept
to real, honest progress tracking with no loss-aversion/FOMO framing,
no fake scarcity, no "you're about to lose your streak!" pressure
notifications.

Data source and why: `services/user_analytics.py`'s event log looked
like the obvious source at first, but its `/api/analytics/track` sender
is only wired into 3 frontend files (dashboard.html, chart-analysis.html,
js/nav.js) -- nowhere near comprehensive enough to badge real usage
across the whole product without silently under-crediting most users
(effectively a fabrication-by-omission problem, not a real "no activity"
signal). Instead this module gets its own dedicated `user_activity_days`
table, populated by record_activity() calls added directly into
services/quota_middleware.py's check_and_increment() and
check_token_budget() -- the two functions every AI-consuming feature on
the site already calls (ai_analysis, chat, stress_lab, company_compare,
chart_analysis, full_analysis, research, report), for BOTH free and
paid users, not gated behind the free-tier points system the way
services/points_service.py's tracking is. One row per user per
calendar day (UTC), deduped -- this table only ever answers "did this
user do at least one real AI-consuming action on this UTC date", never
how many/which.

Badges are pure functions of that real, already-comprehensively-wired
data -- no manual admin grant path, no purchasable badges, nothing that
could be gamed or bought.
"""
import os
import sqlite3
from datetime import date, datetime, timedelta
from typing import Dict, List

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "xfinlab.db")


def _get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_table():
    conn = _get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS user_activity_days (
            user_id INTEGER NOT NULL,
            activity_date TEXT NOT NULL,
            UNIQUE(user_id, activity_date)
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_activity_user
        ON user_activity_days (user_id, activity_date)
    """)
    conn.commit()
    conn.close()


_init_table()


def record_activity(user_id: int) -> None:
    """Best-effort, never raises -- called from quota_middleware.py on
    every AI-consuming feature use, for every logged-in user regardless
    of plan. A failure here must never block the real feature request
    it's piggybacking on."""
    if not user_id:
        return
    today = date.today().isoformat()
    try:
        conn = _get_db()
        conn.execute(
            "INSERT OR IGNORE INTO user_activity_days (user_id, activity_date) VALUES (?, ?)",
            (user_id, today),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


def _compute_streaks(sorted_dates: List[date]) -> Dict:
    """sorted_dates must be ascending, deduplicated. Returns current_streak
    (consecutive days ending today or yesterday -- a streak that hasn't
    been extended in 2+ days is honestly reported as broken/0, not
    carried forward) and longest_streak (best run ever, doesn't require
    it to be current)."""
    if not sorted_dates:
        return {"current_streak": 0, "longest_streak": 0}

    longest = 1
    run = 1
    for i in range(1, len(sorted_dates)):
        if (sorted_dates[i] - sorted_dates[i - 1]).days == 1:
            run += 1
        else:
            run = 1
        longest = max(longest, run)

    today = date.today()
    last_active = sorted_dates[-1]
    gap_from_today = (today - last_active).days
    if gap_from_today > 1:
        current = 0  # streak broken -- more than a day since last real activity
    else:
        # Walk backward from the last active day counting the consecutive run.
        current = 1
        for i in range(len(sorted_dates) - 1, 0, -1):
            if (sorted_dates[i] - sorted_dates[i - 1]).days == 1:
                current += 1
            else:
                break

    return {"current_streak": current, "longest_streak": longest}


# Each condition is a pure function of the real stats computed below --
# no badge here can be granted, bought, or admin-overridden outside this
# list. Ordered roughly by how quickly a genuine user reaches them.
_ACHIEVEMENTS = [
    {"key": "first_session", "label": "First Session", "description": "Used an AI-powered feature for the first time.",
     "condition": lambda s: s["total_active_days"] >= 1},
    {"key": "streak_3", "label": "3-Day Streak", "description": "Active 3 days in a row.",
     "condition": lambda s: s["longest_streak"] >= 3},
    {"key": "streak_7", "label": "7-Day Streak", "description": "Active 7 days in a row.",
     "condition": lambda s: s["longest_streak"] >= 7},
    {"key": "streak_30", "label": "30-Day Streak", "description": "Active 30 days in a row.",
     "condition": lambda s: s["longest_streak"] >= 30},
    {"key": "active_10", "label": "Regular Researcher", "description": "10 total active days.",
     "condition": lambda s: s["total_active_days"] >= 10},
    {"key": "active_50", "label": "Dedicated Researcher", "description": "50 total active days.",
     "condition": lambda s: s["total_active_days"] >= 50},
    {"key": "active_100", "label": "Veteran Researcher", "description": "100 total active days.",
     "condition": lambda s: s["total_active_days"] >= 100},
]


def get_achievements(user_id: int) -> Dict:
    """Read-only. Returns real stats plus which badges are unlocked and
    the single nearest not-yet-unlocked badge (for a simple "next
    milestone" progress hint) -- never a fabricated ETA, since usage
    frequency isn't predictable."""
    conn = _get_db()
    rows = conn.execute(
        "SELECT activity_date FROM user_activity_days WHERE user_id=? ORDER BY activity_date ASC",
        (user_id,),
    ).fetchall()
    conn.close()

    dates = [datetime.strptime(r["activity_date"], "%Y-%m-%d").date() for r in rows]
    streaks = _compute_streaks(dates)
    stats = {
        "total_active_days": len(dates),
        "current_streak": streaks["current_streak"],
        "longest_streak": streaks["longest_streak"],
    }

    unlocked = []
    locked = []
    for a in _ACHIEVEMENTS:
        entry = {"key": a["key"], "label": a["label"], "description": a["description"]}
        if a["condition"](stats):
            unlocked.append(entry)
        else:
            locked.append(entry)

    return {
        "stats": stats,
        "unlocked": unlocked,
        "next_badge": locked[0] if locked else None,
        "total_badges": len(_ACHIEVEMENTS),
        "unlocked_count": len(unlocked),
    }
