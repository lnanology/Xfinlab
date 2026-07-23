"""
Social login (task #330/#331): "Sign in with Google" + "Login with LINE".

Both are OpenID Connect flows where the identity provider hands back a
signed JWT (id_token) we verify OURSELVES against the provider's public
JWKS, using PyJWT's PyJWKClient -- already a project dependency (see
backend/auth/jwt_handler.py's PYSEC-2026-1325 migration note), so this
adds zero new third-party packages (no google-auth/authlib needed).

Google: client-side "Sign In With Google" button (Google Identity
Services JS) hands the frontend a signed id_token directly -- no
redirect/callback needed, just POST /api/auth/google {credential}.

LINE: LINE's OAuth implementation requires the classic
authorize->redirect->code->token-exchange dance (no equivalent of
Google's client-side GIS button), so this is a full-page redirect flow:
  1. GET /api/auth/line/start  -> 302 to LINE's authorize URL
  2. LINE redirects back to    -> GET /api/auth/line/callback?code=...
  3. callback exchanges code for id_token, verifies it, finds/creates
     the user, then 302-redirects to login.html?social_token=<ourJWT>
     so the frontend can pick it up exactly like a normal login.

Both providers share _find_or_create_oauth_user() below with
services/whatsapp_otp_service.py's phone-based version following the
same pattern (see that file for phone/WhatsApp instead of email/OAuth).
"""
import os
import secrets
import sqlite3
import requests
import jwt
from jwt import PyJWKClient
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

from backend.auth.jwt_handler import create_access_token
from auth.password import hash_password
from services.audit_log_service import log_action
from services.request_ip import get_client_ip

router = APIRouter()

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "xfinlab.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_oauth_columns():
    """Same additive, try/except ALTER TABLE pattern already used by
    backend/auth/email_verification.py's email_verified column -- no
    formal migrations system in this codebase, so this stays consistent
    with the established convention rather than introducing a new one."""
    conn = get_db()
    for stmt in (
        "ALTER TABLE users ADD COLUMN oauth_provider TEXT",
        "ALTER TABLE users ADD COLUMN oauth_id TEXT",
        "ALTER TABLE users ADD COLUMN phone TEXT",
        "ALTER TABLE users ADD COLUMN phone_verified INTEGER DEFAULT 0",
    ):
        try:
            conn.execute(stmt)
        except Exception:
            pass
    conn.commit()
    conn.close()


_ensure_oauth_columns()


def find_or_create_oauth_user(email: str, name: str, provider: str, provider_id: str):
    """Shared by Google + LINE (email-based identity). Returns the users
    row (sqlite3.Row). If an account with this email already exists
    (e.g. they originally signed up with email/password), it's reused
    as-is and just gets the oauth_provider/oauth_id linked -- signing in
    with Google using the same email as an existing account should log
    into that SAME account, not create a duplicate."""
    conn = get_db()
    row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    if row:
        if not row["oauth_provider"]:
            conn.execute(
                "UPDATE users SET oauth_provider = ?, oauth_id = ? WHERE id = ?",
                (provider, provider_id, row["id"]),
            )
            conn.commit()
        conn.close()
        return row

    # New account. password column is NOT NULL with no OAuth-aware schema
    # change made -- store a random, never-typed placeholder hash so a
    # password-login attempt can never succeed for an OAuth-only account,
    # without altering the existing column constraint.
    placeholder_password = hash_password(secrets.token_urlsafe(32))
    cursor = conn.execute(
        "INSERT INTO users (email, password, name, email_verified, oauth_provider, oauth_id) "
        "VALUES (?, ?, ?, 1, ?, ?)",
        (email, placeholder_password, name or email.split("@")[0], provider, provider_id),
    )
    conn.commit()
    user_id = cursor.lastrowid
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return row


def _issue_login_response(row, provider: str, request: Request):
    token = create_access_token({"sub": row["email"], "id": row["id"]})
    log_action(row["id"], f"login:{provider}", get_client_ip(request))
    return {
        "status": "ok",
        "id": row["id"],
        "email": row["email"],
        "name": row["name"],
        "plan": row["plan"],
        "token": token,
    }


# ----------------------------- Google ---------------------------------

GOOGLE_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
_google_jwk_client = None


def _get_google_jwk_client():
    global _google_jwk_client
    if _google_jwk_client is None:
        _google_jwk_client = PyJWKClient(GOOGLE_JWKS_URL)
    return _google_jwk_client


@router.post("/auth/google")
def google_login(body: dict, request: Request):
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    if not client_id:
        raise HTTPException(status_code=503, detail="Google login is not configured on this server yet.")

    credential = body.get("credential")
    if not credential:
        raise HTTPException(status_code=400, detail="Missing credential")

    try:
        signing_key = _get_google_jwk_client().get_signing_key_from_jwt(credential)
        payload = jwt.decode(
            credential,
            signing_key.key,
            algorithms=["RS256"],
            audience=client_id,
            issuer=["https://accounts.google.com", "accounts.google.com"],
        )
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid Google credential: {e}")

    email = payload.get("email")
    if not email:
        raise HTTPException(status_code=400, detail="Google account has no email")
    if not payload.get("email_verified", False):
        raise HTTPException(status_code=400, detail="Google email is not verified")

    row = find_or_create_oauth_user(email, payload.get("name"), "google", payload.get("sub"))
    return _issue_login_response(row, "google", request)


# ------------------------------ LINE ------------------------------------

LINE_AUTHORIZE_URL = "https://access.line.me/oauth2/v2.1/authorize"
LINE_TOKEN_URL = "https://api.line.me/oauth2/v2.1/token"
LINE_JWKS_URL = "https://api.line.me/oauth2/v2.1/certs"
_line_jwk_client = None


def _get_line_jwk_client():
    global _line_jwk_client
    if _line_jwk_client is None:
        _line_jwk_client = PyJWKClient(LINE_JWKS_URL)
    return _line_jwk_client


def _line_redirect_uri():
    # Must match EXACTLY (including trailing slash/scheme) what's
    # registered in the LINE Developers Console for this channel.
    return os.getenv("LINE_LOGIN_REDIRECT_URI", "https://api.xfinlab.com/api/auth/line/callback")


@router.get("/auth/line/start")
def line_login_start(state: str = ""):
    channel_id = os.getenv("LINE_CHANNEL_ID")
    if not channel_id:
        raise HTTPException(status_code=503, detail="LINE login is not configured on this server yet.")
    if not state:
        state = secrets.token_urlsafe(16)
    params = (
        f"?response_type=code&client_id={channel_id}"
        f"&redirect_uri={_line_redirect_uri()}"
        f"&state={state}&scope=openid%20profile%20email"
    )
    return RedirectResponse(LINE_AUTHORIZE_URL + params)


@router.get("/auth/line/callback")
def line_login_callback(request: Request, code: str = "", state: str = "", error: str = ""):
    # Frontend/login page this ultimately lands back on, so the JS there
    # can pick up ?social_token=... (success) or ?social_error=... (failure)
    # from the URL exactly like it would after any other login.
    login_page = "https://www.xfinlab.com/login.html"

    if error or not code:
        return RedirectResponse(f"{login_page}?social_error=line_denied")

    channel_id = os.getenv("LINE_CHANNEL_ID")
    channel_secret = os.getenv("LINE_CHANNEL_SECRET")
    if not channel_id or not channel_secret:
        return RedirectResponse(f"{login_page}?social_error=line_not_configured")

    try:
        token_res = requests.post(
            LINE_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": _line_redirect_uri(),
                "client_id": channel_id,
                "client_secret": channel_secret,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=15,
        )
        token_data = token_res.json()
        id_token = token_data.get("id_token")
        if not id_token:
            return RedirectResponse(f"{login_page}?social_error=line_token_exchange_failed")

        signing_key = _get_line_jwk_client().get_signing_key_from_jwt(id_token)
        payload = jwt.decode(
            id_token,
            signing_key.key,
            algorithms=["RS256"],
            audience=channel_id,
            issuer="https://access.line.me",
        )
    except Exception:
        return RedirectResponse(f"{login_page}?social_error=line_verify_failed")

    # LINE only includes `email` in the id_token if the channel has been
    # granted the (LINE-approval-gated) email permission. Without it,
    # fall back to a synthetic-but-stable placeholder keyed off LINE's
    # own user id (`sub`) so the account is still unique and reusable on
    # repeat logins -- same technique used for WhatsApp phone-only
    # accounts in services/whatsapp_otp_service.py.
    line_sub = payload.get("sub", "")
    email = payload.get("email") or f"line_{line_sub}@line.xfinlab.internal"
    name = payload.get("name") or "LINE User"

    row = find_or_create_oauth_user(email, name, "line", line_sub)
    token = create_access_token({"sub": row["email"], "id": row["id"]})
    log_action(row["id"], "login:line", get_client_ip(request))
    return RedirectResponse(f"{login_page}?social_token={token}")
