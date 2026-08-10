
from pydantic import BaseModel
from typing import Optional

class UserRegister(BaseModel):
    email: str
    password: str
    name: str
    # Slide-puzzle CAPTCHA pass-token from /api/captcha/verify (see
    # services/captcha_service.py). Optional at the model level so a
    # missing/blank value degrades to a clear 400 in register() rather
    # than a generic 422 validation error.
    captcha_token: Optional[str] = None
    # 2026-07-24 anti-abuse batch: self-hosted browser fingerprint hash
    # from js/device-fingerprint.js (canvas+WebGL+screen/locale -> SHA-256,
    # no third-party service). Optional -- an old cached page, a browser
    # without SubtleCrypto, or a blocked script should degrade to "no
    # fingerprint signal" (services/risk_score_service.py treats a missing
    # fingerprint as reuse-count 0), never to a hard registration failure.
    device_fingerprint: Optional[str] = None
    # 2026-07-26 referral system: optional referral code carried through
    # from a `?ref=CODE` link (see login.html reading the query param and
    # api/referral.py generating the link). Optional -- a normal signup
    # with no referral simply skips the reward in register() below.
    ref_code: Optional[str] = None

class UserLogin(BaseModel):
    email: str
    password: str

class UserResponse(BaseModel):
    id: int
    email: str
    name: str
    plan: str
    token: str
    # 2026-07-24 anti-abuse batch: True only for a risk-flagged registration
    # (services/risk_score_service.py's "flag" tier). When True, `token` is
    # deliberately an empty string -- NOT a usable session -- because a
    # stateless JWT has no server-side "is this verified yet" check once
    # issued, so the only real enforcement point is withholding the token
    # entirely until the account's email is verified (see backend/auth/
    # auth.py's login(), which then requires email_verified=1 for any
    # risk_flagged account before issuing a real token). Optional/defaulted
    # so every other UserResponse call site (social login, WhatsApp OTP,
    # normal login) is unaffected.
    requires_verification: Optional[bool] = False
    # 2026-08-10 (task #761, AJ: "登入後身份以男女公仔頭 ICON 取代，加自定
    # 名字"): avatar_gender is 'm'/'f'/None (None = not chosen yet, frontend
    # falls back to a neutral icon). oauth_provider ('line'/'google'/
    # 'whatsapp'/None) lets the frontend know when to apply LINE's
    # "truncate the long display name to 1 char by default" rule (AJ:
    # "LINE號太長只顯示你位字") instead of showing the name in full.
    avatar_gender: Optional[str] = None
    oauth_provider: Optional[str] = None

class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    avatar_gender: Optional[str] = None
