
import sqlite3
import os
from fastapi import APIRouter, HTTPException, Request
from auth.user_model import UserRegister, UserLogin, UserResponse, ProfileUpdate
from auth.password import hash_password, verify_password
# 2026-07-11 fix: 呢度之前用緊短路徑 `from auth.jwt_handler import ...`，
# 但codebase入面第9個地方（quota_middleware/referral/quota/analytics/
# onboarding/feedback/admin/watchlist）全部用緊長路徑
# `from backend.auth.jwt_handler import ...`。Python嘅import系統將呢兩條
# 路徑當做兩個唔同嘅module object，各自獨立執行一次jwt_handler.py嘅
# top-level code——如果JWT_SECRET env var冇set，兩個instance會各自
# 生成一個唔同嘅random secret，導致喺呢度create嘅token喺其他地方
# verify唔到（反之亦然）。生產環境因為JWT_SECRET有set，兩個instance
# 讀返同一個env var值，暫時冇壞，但呢個fragility喺local testing已經
# 引致混淆，值得徹底消除。統一用返長路徑。
from backend.auth.jwt_handler import create_access_token
from services.email_service import EmailService
from services.audit_log_service import log_action, count_recent_failed_logins
from services.request_ip import get_client_ip
from auth.email_verification import send_verification_email
from infrastructure.event_bus import EventBus
from services.disposable_email_domains import is_disposable_email
from services.captcha_service import is_verify_token_valid
from services.risk_score_service import compute_registration_risk, record_device_fingerprint

router = APIRouter()

# --- "user_registered" subscribers (Phase 3, Event Bus first real use) ---
# Previously these three were three separate, tightly-coupled calls inside
# register() itself. Splitting them into independent subscribers means
# adding a fourth "on register" behavior later (e.g. a Slack ping to admin,
# seeding the onboarding table) is a new subscribe() call, not an edit to
# the registration endpoint. Behavior is unchanged -- same three actions,
# same silent-failure-doesn't-block-registration guarantee, now enforced
# by EventBus.publish()'s per-subscriber exception isolation instead of a
# manual try/except.


def _on_user_registered_send_welcome_email(data):
    EmailService.send_welcome(data["email"], data["name"])


def _on_user_registered_send_verification_email(data):
    send_verification_email(data["user_id"], data["email"], data["name"])


def _on_user_registered_audit_log(data):
    log_action(data["user_id"], "register", data.get("ip"))


# 2026-08-25 (AJ: "Free tier 加鈎: 送 API key(low quota)畀所有免費用戶 —
# 開發者一裝就唔走"): every new signup now gets a working Intelligence API
# key immediately, not just users who separately find intelligence-
# api.html's self-serve signup form. Uses api_key_service.issue_key() --
# the SAME api_keys table dashboard.html's "Intelligence API 金鑰" panel
# already reads via get_my_key_status() (task #724) -- rather than
# issue_self_serve_free_key()'s separate self_serve_api_keys table, so the
# key shows up in the dashboard with zero frontend changes. tier="free"
# maps to the same 100 calls/day quota (services/intelligence_quota_
# service.py's TIER_LIMITS) every other free-tier key gets. Reuses the
# same email template api/intelligence.py's self-serve endpoint sends
# (services.api_key_service.send_api_key_email) so a developer who signs
# up via the consumer site sees identical, consistent messaging to one who
# signs up via the API page directly. Best-effort like every other
# subscriber here -- EventBus.publish() isolates this from the other three
# and from registration succeeding at all.
def _on_user_registered_issue_free_api_key(data):
    from services.api_key_service import issue_key, send_api_key_email
    result = issue_key(data["email"], tier="free")
    if "key" in result:
        send_api_key_email(data["email"], result["key"])


EventBus.subscribe("user_registered", _on_user_registered_send_welcome_email)
EventBus.subscribe("user_registered", _on_user_registered_send_verification_email)
EventBus.subscribe("user_registered", _on_user_registered_audit_log)
EventBus.subscribe("user_registered", _on_user_registered_issue_free_api_key)
# NOTE: this file lives at backend/auth/auth.py, so it needs to go up TWO
# levels (auth/ -> backend/ -> repo root) to reach the canonical, Litestream
# -backed xfinlab.db that every other service reads/writes. A previous
# version of this path only went up one level, silently writing to
# backend/xfinlab.db instead -- see services/db_migration.py for the
# one-time fix that recovers any users stranded there.
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "xfinlab.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# 2026-08-10 (task #761): avatar_gender (this file's ensure_avatar_gender_
# column-triggered ALTER, run from backend/main.py) and oauth_provider
# (backend/auth/social_login.py's _ensure_oauth_columns()) both live on
# `users` but get added by migrations in OTHER modules whose import/call
# order relative to this one isn't guaranteed. Reading a column that
# doesn't exist yet on a sqlite3.Row raises IndexError, so every read of
# either column in this file goes through this helper instead of `row[col]`.
def _safe_col(row, col, default=None):
    try:
        return row[col] if col in row.keys() else default
    except Exception:
        return default

def init_users_table():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            name TEXT NOT NULL,
            plan TEXT DEFAULT 'free',
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    # 2026-07-24 anti-abuse batch: marks an account produced by a
    # medium-risk registration (services/risk_score_service.py's "flag"
    # tier -- e.g. same device fingerprint reused several times, or
    # several signups from the same IP within the hour). Same guarded
    # ALTER TABLE pattern already used by backend/auth/email_verification.
    # py for email_verified -- try/except so re-running this on a DB that
    # already has the column is a silent no-op, not a crash.
    try:
        conn.execute("ALTER TABLE users ADD COLUMN risk_flagged INTEGER DEFAULT 0")
    except Exception:
        pass
    # 2026-07-27 referral-driven annual-Pro reward batch: a real paying
    # subscription now needs an expiry (previously `plan` was a permanent
    # admin-set flag with no time dimension -- fine for manual comps, not
    # fine for "1 year of Pro"). NULL means "no expiry" (preserves exact
    # existing behavior for every row created before this column existed,
    # and for admin's plain upgrade_user()/downgrade_user() actions, which
    # still don't set it). Same guarded ALTER pattern as risk_flagged above.
    try:
        conn.execute("ALTER TABLE users ADD COLUMN plan_expires_at TEXT DEFAULT NULL")
    except Exception:
        pass
    conn.commit()
    conn.close()

init_users_table()

@router.post("/auth/register", response_model=UserResponse)
def register(user: UserRegister, request: Request):
    # 2026-07-21: block known disposable/temp-mail domains -- these let
    # one person spin up unlimited throwaway inboxes and register
    # unlimited accounts, defeating the per-account free-tier quota.
    if is_disposable_email(user.email):
        raise HTTPException(
            status_code=400,
            detail="Please use a permanent email address. Disposable/temporary email services are not accepted.",
        )
    # 2026-07-21: require a passed slide-puzzle CAPTCHA (see
    # services/captcha_service.py + js/captcha-widget.js on login.html)
    # -- second anti-bot layer alongside the disposable-email blocklist
    # above and the existing per-IP rate limiter.
    if not is_verify_token_valid(user.captcha_token):
        raise HTTPException(
            status_code=400,
            detail="Please complete the slide verification before creating an account.",
        )

    # 2026-07-24 anti-abuse batch ("仲有4層完全未做 係免費就去做啦"): combine
    # MX-record deliverability + device-fingerprint reuse + same-IP
    # registration frequency into one risk score (services/risk_score_
    # service.py) rather than each being its own separate gate. A
    # confirmed high-risk attempt (score>=70 -- e.g. a domain that can't
    # receive mail at all) is rejected outright, same tier as the
    # disposable-email/captcha checks above; a medium-risk one (40-69) is
    # still allowed to register but gets flagged so login() below requires
    # email verification first.
    client_ip = get_client_ip(request)
    risk = compute_registration_risk(user.email, client_ip, user.device_fingerprint)
    if risk["action"] == "reject":
        raise HTTPException(
            status_code=403,
            detail="We couldn't verify this email address is able to receive mail, or this registration matched several risk signals. Please use a permanent, working email address.",
        )
    risk_flagged = 1 if risk["action"] == "flag" else 0

    conn = get_db()
    try:
        hashed = hash_password(user.password)
        cursor = conn.execute(
            "INSERT INTO users (email, password, name, risk_flagged) VALUES (?, ?, ?, ?)",
            (user.email, hashed, user.name, risk_flagged)
        )
        conn.commit()
        user_id = cursor.lastrowid
        # 2026-07-24: a risk-flagged account does NOT get a usable token at
        # registration time -- see UserResponse.requires_verification's
        # docstring for why this is the only real enforcement point for a
        # stateless JWT. The account still gets created (so the emailed
        # verification link in send_verification_email() below has a real
        # user_id to attach to), just without an immediately-usable session.
        token = "" if risk_flagged else create_access_token({"sub": user.email, "id": user_id})
        EventBus.publish("user_registered", {
            "user_id": user_id,
            "email": user.email,
            "name": user.name,
            "ip": client_ip,
        })
        # Recorded AFTER the insert succeeds so a duplicate-email failure
        # below (IntegrityError) never records a fingerprint for an
        # account that doesn't actually exist. Also logs the risk score/
        # reasons onto the existing audit trail (reuses log_action() --
        # no new table needed just to keep this visible for later review).
        record_device_fingerprint(user.device_fingerprint, user.email)
        if risk["reasons"]:
            log_action(user_id, f"register_risk_score:{risk['score']}:{','.join(risk['reasons'])}", client_ip)
        # 2026-07-26 referral system: apply the referral reward if a code
        # was carried through (see UserRegister.ref_code + login.html
        # reading `?ref=`). Deliberately fail-open -- a bad/expired/
        # missing code, or any unexpected error in the referral service,
        # must never block or fail an otherwise-successful registration.
        if user.ref_code:
            try:
                from services.referral_service import ReferralService
                ReferralService.use_code(user.ref_code, user_id)
            except Exception:
                pass
        return UserResponse(
            id=user_id, email=user.email, name=user.name, plan="free", token=token,
            requires_verification=bool(risk_flagged),
        )
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="Email already registered")
    finally:
        conn.close()

LOGIN_LOCKOUT_THRESHOLD = 5   # failed attempts
LOGIN_LOCKOUT_WINDOW_MINUTES = 15

@router.post("/auth/login", response_model=UserResponse)
def login(user: UserLogin, request: Request):
    # Brute-force / credential-stuffing guard: block further attempts for
    # this email once it's racked up too many recent failures, using the
    # login_failed audit trail added earlier. Checked before touching the
    # users table at all, so a locked-out email can't be used to keep
    # probing passwords. Fails open (never locks anyone out) if the audit
    # log query itself errors -- see count_recent_failed_logins().
    recent_failures = count_recent_failed_logins(user.email, minutes=LOGIN_LOCKOUT_WINDOW_MINUTES)
    if recent_failures >= LOGIN_LOCKOUT_THRESHOLD:
        raise HTTPException(
            status_code=429,
            detail=f"登入失敗次數過多，請{LOGIN_LOCKOUT_WINDOW_MINUTES}分鐘後再試。",
        )

    conn = get_db()
    row = conn.execute("SELECT * FROM users WHERE email = ?", (user.email,)).fetchone()
    conn.close()
    if not row or not verify_password(user.password, row["password"]):
        # user_id=None is now allowed (see services/db_migration.py --
        # audit_logs.user_id nullable migration) so failed attempts are
        # visible for brute-force/credential-stuffing monitoring, not just
        # successful logins.
        log_action(None, f"login_failed:{user.email}", get_client_ip(request))
        raise HTTPException(status_code=401, detail="Invalid email or password")
    # 2026-07-24 anti-abuse batch: a risk-flagged account (services/
    # risk_score_service.py's "flag" tier at registration -- see
    # register()) never got a usable token at signup time; it can only
    # log in for real once the emailed verification link has been
    # clicked (row["email_verified"], set by backend/auth/email_
    # verification.py's verify_email()). This is the actual enforcement
    # point -- see UserResponse.requires_verification's docstring for why
    # withholding-the-token is the only mechanism that works for a
    # stateless JWT. Password check above still runs FIRST so this never
    # leaks "this email is flagged" to someone who doesn't already know
    # the correct password.
    if row["risk_flagged"] and not row["email_verified"]:
        raise HTTPException(
            status_code=403,
            detail="Please verify your email address before logging in. Check your inbox for the verification link, or use the resend option.",
        )
    token = create_access_token({"sub": row["email"], "id": row["id"]})
    log_action(row["id"], "login", get_client_ip(request))
    return UserResponse(
        id=row["id"], email=row["email"], name=row["name"], plan=row["plan"], token=token,
        avatar_gender=_safe_col(row, "avatar_gender"), oauth_provider=_safe_col(row, "oauth_provider"),
    )

@router.get("/auth/me")
def get_me(token: str):
    from backend.auth.jwt_handler import verify_token
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    conn = get_db()
    row = conn.execute("SELECT * FROM users WHERE email = ?", (payload["sub"],)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    return {
        "id": row["id"], "email": row["email"], "name": row["name"], "plan": row["plan"],
        "avatar_gender": _safe_col(row, "avatar_gender"), "oauth_provider": _safe_col(row, "oauth_provider"),
        "name_is_custom": bool(_safe_col(row, "name_is_custom", 0)),
    }

# 2026-08-10 (task #761, AJ: "也可改名" / "加可改名字" -- both the mail-
# derived name and the LINE display name need to be user-editable, plus
# the new male/female avatar icon choice). Same token-as-query-param auth
# pattern as get_me() above (this file has no FastAPI dependency-injected
# bearer scheme anywhere else, so this matches the existing convention
# rather than introducing a new one). PUT (not PATCH) for consistency with
# the rest of this codebase's simple REST endpoints; both fields are
# optional so the caller can update just the name, just the avatar, or both.
@router.put("/auth/profile")
def update_profile(update: ProfileUpdate, token: str, request: Request):
    from backend.auth.jwt_handler import verify_token
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")

    name = update.name.strip() if update.name is not None else None
    if name is not None and (not name or len(name) > 40):
        raise HTTPException(status_code=400, detail="Name must be 1-40 characters")

    avatar_gender = update.avatar_gender
    if avatar_gender is not None and avatar_gender not in ("m", "f"):
        raise HTTPException(status_code=400, detail="avatar_gender must be 'm' or 'f'")

    conn = get_db()
    row = conn.execute("SELECT * FROM users WHERE email = ?", (payload["sub"],)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="User not found")

    if name is not None:
        # name_is_custom=1 marks this as a deliberate rename -- see
        # services/db_migration.py's ensure_avatar_gender_column() for why
        # this matters specifically for LINE accounts (their default name
        # is truncated for display; a renamed one is shown in full).
        conn.execute("UPDATE users SET name = ?, name_is_custom = 1 WHERE id = ?", (name, row["id"]))
    if avatar_gender is not None:
        conn.execute("UPDATE users SET avatar_gender = ? WHERE id = ?", (avatar_gender, row["id"]))
    conn.commit()
    row = conn.execute("SELECT * FROM users WHERE id = ?", (row["id"],)).fetchone()
    conn.close()
    log_action(row["id"], "profile_update", get_client_ip(request))
    return {
        "id": row["id"], "email": row["email"], "name": row["name"], "plan": row["plan"],
        "avatar_gender": _safe_col(row, "avatar_gender"), "oauth_provider": _safe_col(row, "oauth_provider"),
        "name_is_custom": bool(_safe_col(row, "name_is_custom", 0)),
    }
