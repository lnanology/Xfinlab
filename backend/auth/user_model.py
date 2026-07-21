
from pydantic import BaseModel, EmailStr
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

class UserLogin(BaseModel):
    email: str
    password: str

class UserResponse(BaseModel):
    id: int
    email: str
    name: str
    plan: str
    token: str
