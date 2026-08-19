"""2026-08-19: shared "a real payment just landed, grant the plan" logic,
extracted out of api/webhooks_stripe.py so api/webhooks_paddle.py's
generalized checkout can call the exact same function instead of a second,
hand-copied implementation. This kind of duplication is exactly what
caused the earlier admin.html bug (api/feedback.py's own ad-hoc auth check
drifting out of sync with api/admin.py's verify_admin() and reporting a
different error code for the same root cause) -- for anything touching
who-gets-charged-what, one implementation shared by every payment
provider is safer than N copies that can quietly diverge.

pricing.html sells 4 real, backend-enforced tiers (basic/pro/proplus/
professional -- see services/token_quota_service.py's PLAN_TOKEN_PCT),
each independently monthly or annual. The one hardcoded special case is
pro+annual, which reuses services/referral_service.py's
mark_annual_pro_payment() (real 1-year expiry + referral reward) -- the
same function admin.html's manual "mark annual pro" button already calls,
so an annual Pro sale behaves identically no matter which of the three
trigger points (admin button / Paddle / Stripe) fired it. Every other
plan/cycle combo just sets plan + a rolling plan_expires_at directly.
"""
import datetime
import os
import sqlite3

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "xfinlab.db")

VALID_PLANS = {"basic", "pro", "proplus", "professional"}
VALID_CYCLES = {"monthly", "annual"}


def grant_plan(user_id: int, plan: str, cycle: str) -> dict:
    """Call this once a payment provider has confirmed a real, paid charge
    (never on a mere 'checkout started' or 'trial began' event -- see each
    webhook file's own PAID_EVENTS-style filter for that gate)."""
    if plan not in VALID_PLANS:
        raise ValueError(f"Unknown plan {plan!r}")
    if cycle not in VALID_CYCLES:
        raise ValueError(f"Unknown billing cycle {cycle!r}")

    if cycle == "annual" and plan == "pro":
        from services.referral_service import ReferralService
        result = ReferralService.mark_annual_pro_payment(user_id)
        return {"action": "annual_pro_granted", "result": result}

    days = 370 if cycle == "annual" else 35
    expires_at = (datetime.datetime.utcnow() + datetime.timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE users SET plan=?, plan_expires_at=? WHERE id=?", (plan, expires_at, user_id))
    conn.commit()
    conn.close()
    return {"action": f"{plan}_{cycle}_granted", "plan_expires_at": expires_at}
