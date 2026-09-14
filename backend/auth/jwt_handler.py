
import os
import secrets
import logging
from datetime import datetime, timedelta
# Migrated from python-jose to PyJWT (2026-07-18): python-jose bundles
# the `ecdsa` package as a transitive dependency, which has a known,
# unfixed timing side-channel (PYSEC-2026-1325 / the "Minerva" attack)
# in its ECDSA signing path. This app only ever signs/verifies with
# HS256 (HMAC, see ALGORITHM below) -- it never calls into ecdsa's
# vulnerable code at all -- so this wasn't actually exploitable here,
# but PyJWT has no ecdsa dependency for HS256 use, so migrating removes
# the flagged CVE from the dependency tree entirely rather than just
# noting "we don't hit that code path." API is a drop-in match
# (jwt.encode/jwt.decode with the same argument shapes), only the
# exception type changed (jwt.PyJWTError instead of jose's JWTError).
import jwt

from backend.auth.token_revocation import is_jti_revoked, is_issued_before_invalidation

logger = logging.getLogger(__name__)

# SECURITY: never fall back to a hardcoded secret. A hardcoded fallback here
# is committed to a GitHub repo, meaning anyone who can read the source can
# forge tokens for ANY account -- including the admin account (api/admin.py
# checks payload["sub"] == ADMIN_EMAIL, nothing else). If JWT_SECRET isn't
# set in Railway, generate a random per-process secret instead: this keeps
# the app running (no crash-loop) but guarantees no attacker can know the
# signing key in advance. The tradeoff is that existing tokens are
# invalidated on every restart until JWT_SECRET is actually configured --
# a one-time "please log in again" is a fair price for closing a full
# account-takeover hole. Set JWT_SECRET in Railway to a long random string
# (e.g. `python3 -c "import secrets; print(secrets.token_hex(32))"`) to fix
# this properly and avoid the forced-logout-on-restart behavior.
SECRET_KEY = os.getenv("JWT_SECRET")
if not SECRET_KEY:
    SECRET_KEY = secrets.token_hex(32)
    logger.warning(
        "JWT_SECRET env var is NOT set -- using a random per-process secret "
        "instead of a hardcoded fallback. All existing tokens are now "
        "invalid and users will need to log in again. Set JWT_SECRET in "
        "Railway's environment variables to a long random string to fix "
        "this permanently."
    )
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days

def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    now = datetime.utcnow()
    expire = now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    # 2026-09-14 addition (security audit gap #2 -- JWT revocation): `jti`
    # gives POST /auth/logout something unique to revoke without touching
    # any other session for the same user; `iat` lets a password reset
    # invalidate every token issued before the reset in one shot (see
    # backend/auth/token_revocation.py). Both are purely additive claims --
    # no existing caller reads or depends on them, so this changes nothing
    # for any code that just does verify_token(token)["sub"]/["id"].
    to_encode.update({
        "exp": expire,
        "iat": now,
        "jti": secrets.token_hex(16),
    })
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def verify_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None

    # 2026-09-14 addition: reject a token that was explicitly logged out
    # (by jti) or whose owner has since reset their password (by iat vs.
    # that email's invalidation cutoff). Tokens issued before this change
    # have no jti/iat and simply skip both checks -- treated as not
    # revoked, same as always, until they expire naturally.
    if is_jti_revoked(payload.get("jti")):
        return None
    if is_issued_before_invalidation(payload.get("sub"), payload.get("iat")):
        return None

    return payload
