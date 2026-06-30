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
    return {"referral_code": code, "referral_link": f"https://finlab-ai.vercel.app?ref={code}"}

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
    return ReferralService.get_stats(payload["id"])
