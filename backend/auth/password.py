from passlib.context import CryptContext

# 2026-09-14 migration (security audit gap #4): sha256_crypt was the only
# scheme -- every new hash was sha256_crypt (a plain iterated-hash
# construction, not designed to resist GPU/ASIC cracking the way bcrypt is).
# bcrypt is now listed first, so hash_password() (used by registration and
# password-reset) starts producing bcrypt hashes immediately. sha256_crypt
# stays in the list purely so verify_password() can still check existing
# users' already-stored sha256_crypt hashes -- nobody is forced to reset
# their password for this migration to take effect. `deprecated="auto"`
# flags any non-bcrypt hash (i.e. every pre-existing sha256_crypt hash) as
# needing an upgrade, which verify_and_update_password() below acts on.
pwd_context = CryptContext(schemes=["bcrypt", "sha256_crypt"], deprecated="auto")

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

def verify_and_update_password(plain: str, hashed: str):
    """Same check as verify_password(), but also transparently upgrades a
    deprecated (sha256_crypt) hash to bcrypt on a successful login -- the
    standard passlib pattern for a zero-downtime, no-forced-reset migration.
    Returns (is_valid, new_hash_or_None). Callers should, on is_valid=True
    and new_hash not None, persist new_hash over the stored hash for that
    user -- see backend/auth/auth.py's login()."""
    return pwd_context.verify_and_update(plain, hashed)
