
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
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def verify_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.PyJWTError:
        return None
