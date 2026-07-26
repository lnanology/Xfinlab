from fastapi import APIRouter, HTTPException
from services.referral_service import ReferralService
from backend.auth.jwt_handler import verify_token

router = APIRouter()

@router.get("/referral/code")
def get_referral_code(token: str):
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    code = ReferralService.generate_code(payload["id"])
    # 2026-07-26 fix ("QRCODE及LINK可給新人按直入註冊頁,準確連接"): was
    # `https://xfinlab.com?ref={code}` -- the bare homepage never read
    # `?ref=`, so a clicked link led nowhere useful. Points straight at
    # the actual signup page (login.html has both sign-in and register
    # tabs; there's no separate register.html) with the code preserved,
    # and login.html now reads + forwards it (see login.html's inline
    # script + backend/auth/auth.py's register()).
    return {"referral_code": code, "referral_link": f"https://www.xfinlab.com/login.html?ref={code}"}

@router.post("/referral/use/{code}")
def use_referral(code: str, token: str):
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    return ReferralService.use_code(code, payload["id"])

@router.get("/referral/stats")
def get_stats(token: str):
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    stats = ReferralService.get_stats(payload["id"])
    # 2026-07-26: fold in the site-wide social-proof count ("已有 XXX 人
    #成功推薦") alongside this user's own progress ("已邀請 X/5 位朋友")
    # so the referral UI can render both from one call.
    stats.update(ReferralService.get_global_stats())
    return stats
