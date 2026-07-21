"""
Slide-puzzle CAPTCHA endpoints -- see services/captcha_service.py for the
full design rationale. Used by js/captcha-widget.js on login.html's
registration form.
"""

from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from services.captcha_service import generate_challenge, verify_challenge

router = APIRouter()


@router.get("/captcha/challenge")
def captcha_challenge():
    return generate_challenge()


class CaptchaVerifyRequest(BaseModel):
    challenge_token: str
    x: float
    elapsed_ms: Optional[int] = None


@router.post("/captcha/verify")
def captcha_verify(req: CaptchaVerifyRequest):
    return verify_challenge(req.challenge_token, req.x, req.elapsed_ms)
