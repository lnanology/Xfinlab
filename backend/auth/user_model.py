
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
