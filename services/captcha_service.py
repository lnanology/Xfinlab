"""
Self-hosted slide-puzzle CAPTCHA (滑動拼圖驗證) -- bot-protection for
signup, added 2026-07-21 alongside the disposable-email blocklist as a
second anti-abuse layer (see backend/auth/auth.py's register()).

Deliberately self-hosted rather than a third-party service (hCaptcha/
reCAPTCHA/Cloudflare Turnstile): no external account, no API key, no
recurring cost, and no third-party script/tracking on the login page --
consistent with this project's general preference for owning its own
infra where the cost of doing so is reasonable (see e.g.
services/finbert_sentiment_service.py's HuggingFace fallback pattern,
or the custom rate limiter instead of a paid WAF).

Honest scope note: like every slide-puzzle captcha (including the
well-known commercial ones this mimics), this raises the bar against
opportunistic scripted signups but is NOT a strong defense against a
determined, purpose-built attacker who reads this source and replicates
the drag interaction. Paired with the existing per-IP rate limiting
(backend/main.py's SlowAPIMiddleware) and the disposable-email blocklist,
it meaningfully raises the cost of mass fake-account creation without
adding a third-party dependency or friction-heavy phone/ID verification.

Design: stateless, JWT-signed challenge tokens (reuses the same
HS256/SECRET_KEY as backend/auth/jwt_handler.py's login tokens) --
no server-side session storage needed, which matters on this project's
single-dyno Railway deployment (no shared Redis/cache between
processes). The background image and puzzle piece are both generated
procedurally with Pillow (gradient + random shapes) rather than using
real photos, so there's no image-asset dependency either.
"""

import io
import random
import base64
from datetime import datetime, timedelta, timezone

import jwt
from PIL import Image, ImageDraw

from backend.auth.jwt_handler import SECRET_KEY

ALGORITHM = "HS256"
CHALLENGE_EXPIRE_SECONDS = 120
VERIFY_TOKEN_EXPIRE_SECONDS = 300
TOLERANCE_PX = 6
MIN_HUMAN_MS = 150  # near-instant submission suggests a replayed (x, token) pair, not a real drag

IMG_WIDTH = 320
IMG_HEIGHT = 160
PIECE_SIZE = 42


def _random_background(width: int, height: int) -> Image.Image:
    """Procedurally generated diagonal-gradient background with a
    handful of scattered shapes for visual texture -- gives the puzzle
    notch something to contrast against without needing a real photo
    library (and the accompanying licensing/storage concerns)."""
    img = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(img)
    c1 = tuple(random.randint(25, 90) for _ in range(3))
    c2 = tuple(random.randint(120, 210) for _ in range(3))
    for x in range(width):
        ratio = x / width
        r = int(c1[0] + (c2[0] - c1[0]) * ratio)
        g = int(c1[1] + (c2[1] - c1[1]) * ratio)
        b = int(c1[2] + (c2[2] - c1[2]) * ratio)
        draw.line([(x, 0), (x, height)], fill=(r, g, b))
    for _ in range(7):
        x0 = random.randint(0, width)
        y0 = random.randint(0, height)
        r = random.randint(14, 38)
        shade = tuple(max(0, min(255, c + random.randint(-25, 25))) for c in c2)
        draw.ellipse([x0 - r, y0 - r, x0 + r, y0 + r], fill=shade)
    return img


def _puzzle_piece_mask(size: int) -> Image.Image:
    """Classic slide-captcha silhouette: a square piece with a rounded
    knob bump on the right edge and a matching notch on the left edge."""
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    draw.rectangle([0, 0, size - 1, size - 1], fill=255)
    knob_r = max(4, size // 5)
    mid = size // 2
    draw.ellipse([size - knob_r, mid - knob_r, size + knob_r, mid + knob_r], fill=255)
    draw.ellipse([-knob_r, mid - knob_r, knob_r, mid + knob_r], fill=0)
    return mask


def _to_data_uri(im: Image.Image) -> str:
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def generate_challenge() -> dict:
    bg = _random_background(IMG_WIDTH, IMG_HEIGHT)
    piece_size = PIECE_SIZE
    y = random.randint(10, IMG_HEIGHT - piece_size - 10)
    # Leave room on the left for the piece's resting/start position and
    # on the right for a bit of margin.
    target_x = random.randint(piece_size + 30, IMG_WIDTH - piece_size - 10)

    mask = _puzzle_piece_mask(piece_size)
    piece_img = bg.crop((target_x, y, target_x + piece_size, y + piece_size)).convert("RGBA")
    piece_img.putalpha(mask)

    # Darken the notch on the background so the visitor can see where
    # the piece needs to slide to.
    bg_with_notch = bg.copy()
    dark_mask = mask.point(lambda p: 160 if p > 0 else 0)
    darkening = Image.new("RGBA", (piece_size, piece_size), (0, 0, 0, 160))
    darkening.putalpha(dark_mask)
    bg_with_notch.paste(darkening, (target_x, y), darkening)

    challenge_token = jwt.encode(
        {
            "target_x": target_x,
            "y": y,
            "piece_size": piece_size,
            "exp": datetime.now(timezone.utc) + timedelta(seconds=CHALLENGE_EXPIRE_SECONDS),
            "typ": "captcha_challenge",
        },
        SECRET_KEY,
        algorithm=ALGORITHM,
    )

    return {
        "background_image": _to_data_uri(bg_with_notch),
        "piece_image": _to_data_uri(piece_img),
        "piece_y": y,
        "piece_size": piece_size,
        "img_width": IMG_WIDTH,
        "img_height": IMG_HEIGHT,
        "challenge_token": challenge_token,
    }


def verify_challenge(challenge_token: str, submitted_x, elapsed_ms=None) -> dict:
    if not challenge_token:
        return {"valid": False, "reason": "missing_token"}
    try:
        payload = jwt.decode(challenge_token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return {"valid": False, "reason": "expired_or_invalid"}

    if payload.get("typ") != "captcha_challenge":
        return {"valid": False, "reason": "wrong_token_type"}

    target_x = payload.get("target_x")
    try:
        submitted_x = float(submitted_x)
    except (TypeError, ValueError):
        return {"valid": False, "reason": "invalid_position"}

    if target_x is None or abs(submitted_x - target_x) > TOLERANCE_PX:
        return {"valid": False, "reason": "position_mismatch"}

    if elapsed_ms is not None and elapsed_ms < MIN_HUMAN_MS:
        return {"valid": False, "reason": "too_fast"}

    verify_token = jwt.encode(
        {
            "captcha_passed": True,
            "exp": datetime.now(timezone.utc) + timedelta(seconds=VERIFY_TOKEN_EXPIRE_SECONDS),
            "typ": "captcha_verified",
        },
        SECRET_KEY,
        algorithm=ALGORITHM,
    )
    return {"valid": True, "verify_token": verify_token}


def is_verify_token_valid(verify_token: str) -> bool:
    """Used by backend/auth/auth.py's register() to confirm a valid,
    unexpired, unused-for-anything-else captcha pass was attached to
    this specific registration request."""
    if not verify_token:
        return False
    try:
        payload = jwt.decode(verify_token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return False
    return payload.get("typ") == "captcha_verified" and payload.get("captcha_passed") is True
