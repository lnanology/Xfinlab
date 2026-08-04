"""Growth OS Phase 7 (2026-08-04): AI Video Engine -- turns today's real
free signals (api/market_pulse.py's _compute_free_signals(), the exact
same data free-signals.html/the Telegram push/the email digest already
use) into a short narrated video for distribution channels where a text
post gets no traction but a short video does.

Honesty note on scope (matches this codebase's standing anti-
fabrication rule -- see e.g. stress-lab.html's Monte Carlo fix,
services/widget_service.py's "real signal-strength heatmap, not a
fabricated price-change one"): this renders REAL K-line data (last ~20
daily bars fetched via services/technical_analysis_service.py, the same
OHLC source every chart page already uses) as static candlestick slide
images, one per featured signal, each narrated by real TTS
(services/tts_service.py) and timed to match its own narration clip's
actual duration. It is a data-slide-plus-narration video, not a fully
animated chart-drawing sequence -- frame-by-frame chart animation would
require a much larger rendering pipeline than this scope justifies, and
this docstring says so plainly rather than overselling it.

Pipeline (all via ffmpeg subprocess calls + Pillow-rendered PNG slides):
  1. Build a short script per slide (intro + up to 3 signals + outro).
     Tries an AI rewrite first (_ai_rewrite_narration(), via the same
     ai/ai_router.py used site-wide for chat/analysis) so the narration
     reads like a professional summary instead of a filled-in template;
     falls back to the honest, always-available _SCRIPT templates below
     if the AI call fails, times out, or returns the wrong shape -- this
     is a best-effort quality upgrade, never a hard dependency.
  2. Wrap each line in simple SSML (_build_ssml(): short pauses after
     clause punctuation) -- Google Cloud TTS parses SSML natively, no
     extra dependency. Deliberately limited to <break> only (see
     _build_ssml()'s own docstring): Neural2 voices reject <emphasis>.
  3. TTS each slide's line separately (services/tts_service.py) so each
     slide can be timed to its own narration clip's real duration.
  4. Render each slide as a PNG (size depends on the chosen aspect
     ratio): XFINLAB branding, ticker, direction, confidence, a real
     candlestick strip, and (on signal slides) a burned-in caption of
     the actual narration line, for silent/muted autoplay feeds.
  5. ffmpeg concat-demuxer the images (each held for its matching
     narration duration) into a silent video.
  6. ffmpeg filter_complex-concat the narration clips into one audio
     track, then mux it onto the silent video.

Storage: Railway's filesystem is NOT persisted across deploys/restarts
(litestream.yml only replicates xfinlab.db, never arbitrary files) --
this writes only ONE rolling file (generated_videos/daily_video_latest
.mp4), regenerated on demand, never treated as a permanent archive.
That's an accepted tradeoff for a daily marketing asset, not a defect;
if a durable archive is ever wanted, that's a separate follow-up
(uploading to real object storage), not something to fake here.

is_available() gates on BOTH services.tts_service.is_available() (needs
GOOGLE_TTS_API_KEY) AND the `ffmpeg`/`ffprobe` binaries actually being on
PATH (added via nixpacks.toml's aptPkgs for the Railway build) -- if
either is missing, every entrypoint here returns {"available": False,
"message": ...} instead of raising, so a misconfigured deploy degrades
this ONE optional feature instead of crashing anything else.
"""
import os
import re
import shutil
import subprocess
import tempfile
import textwrap
from datetime import date, datetime, timezone
from typing import List, Optional

from PIL import Image, ImageDraw, ImageFont

from services import tts_service

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "xfinlab.db")
_OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "generated_videos")
_OUTPUT_FILENAME = "daily_video_latest.mp4"

# 2026-08-04: aspect ratio options. "9:16" (vertical) is the original
# Shorts/Reels/TikTok shape; "1:1" (square) suits an Instagram feed
# post; "16:9" (landscape) suits YouTube/X. All layout math in
# _render_slide() below is proportional to whichever (width, height)
# is passed in, not hardcoded to one shape.
_ASPECT_RATIOS = {
    "9:16": (1080, 1920),
    "1:1": (1080, 1080),
    "16:9": (1920, 1080),
}
_DEFAULT_ASPECT = "9:16"

# 2026-08-04: visual themes. "dark" is the original look; "light" is a
# minimal/bright alternative for contexts where a dark video looks out
# of place (e.g. embedded on a light-themed page). "fg" = foreground
# text color (kept a distinct name from the old "white" constant since
# it's dark text in the light theme).
_THEMES = {
    "dark": {
        "bg": (8, 12, 20), "accent": (0, 212, 255), "green": (34, 197, 94),
        "red": (239, 68, 68), "muted": (148, 163, 184), "fg": (226, 232, 240),
    },
    "light": {
        "bg": (248, 250, 252), "accent": (37, 99, 235), "green": (22, 163, 74),
        "red": (220, 38, 38), "muted": (100, 116, 139), "fg": (15, 23, 42),
    },
}
_DEFAULT_THEME = "dark"

# 2026-08-04 expansion (user request: more narration languages): grew
# from zh-HK/en to 7 languages. Kept deliberately narrower than the
# 47-language site-wide i18n convention (same precedent as
# content_repurpose_service.py's EN/ES-only social fan-out) -- these are
# the languages services/tts_service.py has a real Google voice for.
# Every entry here is used as (a) the honest fallback if the AI rewrite
# below fails, and (b) the prompt-language hint for the AI rewrite.
_SCRIPT = {
    "zh-HK": {
        "intro": "XFINLAB 今日AI市場速覽。",
        "signal": "{ticker}，{direction}，信心度 {confidence} 巴仙。",
        "outro": "以上為技術面參考，並非投資建議。想睇更多，去 xfinlab.com。",
        "direction_label": {"bullish": "偏多", "bearish": "偏空", "neutral": "中性"},
    },
    "zh-CN": {
        "intro": "XFINLAB 今日AI市场速览。",
        "signal": "{ticker}，{direction}，信心度 {confidence} 百分比。",
        "outro": "以上为技术面参考，并非投资建议。想了解更多，请访问 xfinlab.com。",
        "direction_label": {"bullish": "偏多", "bearish": "偏空", "neutral": "中性"},
    },
    "zh-TW": {
        "intro": "XFINLAB 今日AI市場速覽。",
        "signal": "{ticker}，{direction}，信心度 {confidence} 百分比。",
        "outro": "以上為技術面參考，並非投資建議。想了解更多，請造訪 xfinlab.com。",
        "direction_label": {"bullish": "偏多", "bearish": "偏空", "neutral": "中性"},
    },
    "en": {
        "intro": "XFINLAB's daily AI market snapshot.",
        "signal": "{ticker}: {direction}, {confidence} percent confidence.",
        "outro": "This is technical reference only, not investment advice. More at xfinlab.com.",
        "direction_label": {"bullish": "bullish", "bearish": "bearish", "neutral": "neutral"},
    },
    "es": {
        "intro": "El resumen diario del mercado con IA de XFINLAB.",
        "signal": "{ticker}: {direction}, {confidence} por ciento de confianza.",
        "outro": "Esto es solo referencia técnica, no es asesoría de inversión. Más en xfinlab.com.",
        "direction_label": {"bullish": "alcista", "bearish": "bajista", "neutral": "neutral"},
    },
    "ja": {
        "intro": "XFINLABの本日のAI市場スナップショットです。",
        "signal": "{ticker}、{direction}、信頼度 {confidence} パーセント。",
        "outro": "これは技術的参考情報であり、投資助言ではありません。詳細は xfinlab.com へ。",
        "direction_label": {"bullish": "強気", "bearish": "弱気", "neutral": "中立"},
    },
    "ko": {
        "intro": "XFINLAB의 오늘의 AI 시장 스냅샷입니다.",
        "signal": "{ticker}, {direction}, 신뢰도 {confidence} 퍼센트.",
        "outro": "이것은 기술적 참고 자료일 뿐이며 투자 조언이 아닙니다. 자세한 내용은 xfinlab.com에서 확인하세요.",
        "direction_label": {"bullish": "강세", "bearish": "약세", "neutral": "중립"},
    },
}

_AI_LANG_NAMES = {
    "zh-HK": "Cantonese (Hong Kong, Traditional Chinese written form, spoken-Cantonese phrasing)",
    "zh-CN": "Mandarin Chinese (Simplified characters, Mainland China)",
    "zh-TW": "Mandarin Chinese (Traditional characters, Taiwan)",
    "en": "English",
    "es": "Spanish",
    "ja": "Japanese",
    "ko": "Korean",
}


def _get_db():
    import sqlite3

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_log_table():
    conn = _get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS video_generation_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            status TEXT NOT NULL,
            message TEXT,
            duration_sec REAL,
            slides_count INTEGER,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    conn.close()


_init_log_table()


def _ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def is_available() -> bool:
    return tts_service.is_available() and _ffmpeg_available()


def _log_generation(status: str, message: str = "", duration_sec: Optional[float] = None, slides_count: int = 0):
    conn = _get_db()
    conn.execute(
        "INSERT INTO video_generation_log (date, status, message, duration_sec, slides_count) VALUES (?, ?, ?, ?, ?)",
        (date.today().isoformat(), status, message, duration_sec, slides_count),
    )
    conn.commit()
    conn.close()


def get_status() -> dict:
    """Admin panel status: availability + the most recent generation
    attempt's outcome (success or failure, with the real error message
    -- never hidden) + the option lists the admin UI needs to populate
    its language/aspect-ratio/theme dropdowns from a single call."""
    conn = _get_db()
    row = conn.execute(
        "SELECT * FROM video_generation_log ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    return {
        "available": is_available(),
        "tts_configured": tts_service.is_available(),
        "ffmpeg_present": _ffmpeg_available(),
        "output_exists": os.path.exists(os.path.join(_OUTPUT_DIR, _OUTPUT_FILENAME)),
        "last_run": dict(row) if row else None,
        "languages": list(_SCRIPT.keys()),
        "aspect_ratios": list(_ASPECT_RATIOS.keys()),
        "themes": list(_THEMES.keys()),
    }


# 2026-08-04 fix: DejaVuSans (the only font this module used to try) has
# NO Chinese/Japanese/Korean glyphs at all -- every CJK character (5 of
# this module's 7 narration languages, plus the bilingual disclaimer
# footer on every slide regardless of language) was rendering as tofu
# boxes. nixpacks.toml now installs fonts-noto-cjk (Noto Sans CJK, one
# font file covering Simplified/Traditional Chinese + Japanese + Korean
# + Latin), tried first; DejaVu stays as a fallback for the Latin-only
# case if that package is ever missing, then Pillow's own bitmap font as
# the last resort so a font problem can never crash the render.
_FONT_CANDIDATES = (
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
)


def _get_font(size: int) -> ImageFont.FreeTypeFont:
    size = max(int(size), 8)
    for path in _FONT_CANDIDATES:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size, index=0)
            except Exception:
                pass
    return ImageFont.load_default()


def _ai_rewrite_narration(signals: List[dict], lang: str) -> Optional[List[str]]:
    """Best-effort quality upgrade: ask the site's existing AI router
    (ai/ai_router.py, the same one chat.html/ai-analysis.html use) to
    rewrite the slide narration into natural, professional spoken copy
    instead of the fixed fill-in-the-blank _SCRIPT templates below.
    Returns None -- never a partial/malformed list -- on ANY failure
    (import error, API error, timeout, wrong line count), so the caller
    always has a clean signal to fall back to the honest template
    script. This is deliberately optional: is_available() and every
    other entrypoint in this module work identically whether or not
    this succeeds."""
    try:
        from ai.ai_router import get_ai_response
    except Exception:
        return None

    lang_name = _AI_LANG_NAMES.get(lang, "English")
    expected_lines = len(signals) + 2  # intro + one per signal + outro

    facts = []
    for s in signals:
        direction = (s.get("confluence_direction") or "neutral").lower()
        facts.append(f"- {s.get('ticker', '?')}: direction={direction}, confidence={s.get('confluence_confidence_pct', 0)}%")
    facts_block = "\n".join(facts)

    prompt = (
        f"You are writing a SHORT spoken video-narration script in {lang_name} for a daily "
        f"AI financial market signal video. Output EXACTLY {expected_lines} lines, one "
        f"sentence per line, no numbering, no markdown, no quotation marks:\n"
        f"Line 1: a 1-sentence intro mentioning XFINLAB and today's AI market snapshot.\n"
        f"Lines 2 through {expected_lines - 1}: one natural sentence per signal below, in a "
        f"professional financial-news tone (not a robotic template), stating the ticker, its "
        f"direction, and its confidence percentage.\n"
        f"Line {expected_lines}: a 1-sentence closing disclaimer that this is technical "
        f"reference only, not investment advice, mentioning xfinlab.com.\n\n"
        f"Signals:\n{facts_block}\n\n"
        f"Output ONLY the {expected_lines} lines of narration text, nothing else."
    )

    try:
        response = get_ai_response(prompt, max_tokens=400, reasoning_effort="low")
    except Exception:
        return None

    if not response:
        return None

    lines = [ln.strip(" \t\"'") for ln in response.strip().split("\n") if ln.strip()]
    if len(lines) != expected_lines:
        return None
    return lines


def _build_ssml(sentence: str) -> str:
    """Wraps a plain narration sentence in simple SSML: a short pause
    after clause-ending punctuation, for more natural pacing than one
    flat monotone run-on. Applied uniformly regardless of whether the
    sentence came from _ai_rewrite_narration() or the _SCRIPT template
    fallback.

    2026-08-04 fix #1 (user-reported: EN/ES/JA/KO video generation
    failing with "TTS API error (400): Invalid SSML. Newer voices like
    Neural2 require valid SSML."): this used to also wrap percentage
    figures in <emphasis level="moderate">. That turned out NOT to be
    the actual bug (Google's docs confirm Neural2 does support
    <emphasis>) -- removing it was a red herring that didn't fix the
    error, kept here only as dead-end history since the real bug (below)
    was hiding underneath it.

    2026-08-04 fix #2 (the REAL bug, found after fix #1 didn't resolve
    the user's repeat report): the punctuation->pause regex used to be
    `re.sub(..., r"\1<break time=\"250ms\"/>", ...)`. In a Python raw
    string, `\"` does NOT become a plain `"` -- Python's raw-string rule
    keeps the backslash AND the quote as two literal characters (the
    backslash only exists to stop the quote from closing the string
    literal). So that regex was actually inserting the literal text
    `<break time=\"250ms\"/>` -- with a real backslash character sitting
    right where the attribute value's opening quote should be -- into
    every single narration line, in every language. That's malformed
    XML (confirmed here by parsing the old output with
    xml.etree.ElementTree: "not well-formed (invalid token)"), which is
    exactly what Google's error message is complaining about. This only
    surfaced as a user-visible failure on Neural2 voices (en/es/ja/ko)
    because Google's error message itself says newer voices *require*
    valid SSML -- Standard/Wavenet (zh-HK/zh-CN/zh-TW) apparently parse
    more leniently and tolerated the malformed tag, which is why this
    bug shipped unnoticed and fix #1 (which didn't touch this line)
    didn't fix anything. Fixed by using single quotes for the attribute
    value (`time='250ms'`) instead of escaped double quotes -- no
    escaping needed inside a double-quoted raw string, so there's no
    slot for this exact mistake to recur. Verified the new output
    parses cleanly with ElementTree for both English and Chinese
    sample sentences."""
    escaped = sentence.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    escaped = re.sub(r"([，,、。.！!？?])", r"\1<break time='250ms'/>", escaped)
    return f"<speak>{escaped}</speak>"


def _render_slide(kind: str, signal: Optional[dict], lang: str, caption_text: str,
                   width: int, height: int, colors: dict) -> Image.Image:
    img = Image.new("RGB", (width, height), colors["bg"])
    draw = ImageDraw.Draw(img)

    pad_x = int(width * 0.055)
    header_font_size = int(height * 0.033)
    sub_font_size = int(height * 0.017)

    # Branding header, every slide.
    draw.text((pad_x, int(height * 0.036)), "XFINLAB", font=_get_font(header_font_size), fill=colors["accent"])
    draw.text((pad_x, int(height * 0.036) + header_font_size + 6), "AI Market Signal",
              font=_get_font(sub_font_size), fill=colors["muted"])
    header_bottom = int(height * 0.036) + header_font_size + sub_font_size + int(height * 0.03)

    if kind == "intro":
        for i, line in enumerate(textwrap.wrap(caption_text, width=max(10, width // 26))):
            draw.text((pad_x, int(height * 0.42) + i * int(height * 0.037)), line,
                      font=_get_font(int(height * 0.032)), fill=colors["fg"])
    elif kind == "outro":
        for i, line in enumerate(textwrap.wrap(caption_text, width=max(10, width // 26))):
            draw.text((pad_x, int(height * 0.42) + i * int(height * 0.033)), line,
                      font=_get_font(int(height * 0.027)), fill=colors["fg"])
    else:  # "signal"
        direction = (signal.get("confluence_direction") or "neutral").lower()
        color = colors["green"] if direction == "bullish" else (colors["red"] if direction == "bearish" else colors["muted"])
        direction_label = _SCRIPT.get(lang, _SCRIPT["en"])["direction_label"].get(direction, direction)

        y = header_bottom
        draw.text((pad_x, y), signal["ticker"], font=_get_font(int(height * 0.062)), fill=colors["fg"])
        y += int(height * 0.075)
        draw.text((pad_x, y), signal.get("label", ""), font=_get_font(int(height * 0.019)), fill=colors["muted"])
        y += int(height * 0.035)
        draw.text((pad_x, y), direction_label.upper(), font=_get_font(int(height * 0.029)), fill=color)
        y += int(height * 0.042)
        conf = signal.get("confluence_confidence_pct")
        if conf is not None:
            draw.text((pad_x, y), f"{conf}%", font=_get_font(int(height * 0.047)), fill=color)
        y += int(height * 0.09)

        # Real candlestick strip from real OHLC data -- honesty per this
        # module's docstring: a genuine (if simplified) chart, not a
        # decorative placeholder. Leaves room below for the caption band
        # + disclaimer footer.
        candles = signal.get("_candles") or []
        candle_bottom = height - int(height * 0.2)
        if candles and candle_bottom > y:
            _draw_candles(draw, candles, x0=pad_x, y0=y, w=width - 2 * pad_x, h=candle_bottom - y, colors=colors)

        # Burned-in caption of the actual spoken sentence -- lets silent/
        # muted autoplay viewers (the default on most social feeds)
        # follow along without sound. Skipped on intro/outro slides
        # since their main on-screen text already IS the caption.
        cap_y = height - int(height * 0.145)
        for i, line in enumerate(textwrap.wrap(caption_text, width=max(10, width // 24))[:3]):
            draw.text((pad_x, cap_y + i * int(height * 0.025)), line,
                      font=_get_font(int(height * 0.021)), fill=colors["fg"])

    # Disclaimer footer on every slide -- same standing site-wide rule
    # (see risk-warning.html / every AI-analysis page) that any signal-
    # like content carries a non-advice disclaimer.
    draw.text((pad_x, height - int(height * 0.073)), "技術面參考，並非投資建議 / Not investment advice",
              font=_get_font(int(height * 0.0125)), fill=colors["muted"])

    return img


def _draw_candles(draw: ImageDraw.ImageDraw, candles: List[dict], x0: int, y0: int, w: int, h: int, colors: dict):
    if not candles or h <= 0:
        return
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]
    top, bottom = max(highs), min(lows)
    span = (top - bottom) or 1.0

    n = len(candles)
    slot_w = w / n
    body_w = max(4, slot_w * 0.55)

    def y_for(price: float) -> float:
        return y0 + h - ((price - bottom) / span) * h

    for i, c in enumerate(candles):
        cx = x0 + slot_w * i + slot_w / 2
        color = colors["green"] if c["close"] >= c["open"] else colors["red"]
        # Wick.
        draw.line([(cx, y_for(c["high"])), (cx, y_for(c["low"]))], fill=color, width=2)
        # Body.
        top_y = y_for(max(c["open"], c["close"]))
        bot_y = y_for(min(c["open"], c["close"]))
        draw.rectangle([cx - body_w / 2, top_y, cx + body_w / 2, max(bot_y, top_y + 2)], fill=color)


def _fetch_candles(ticker: str, limit: int = 20) -> List[dict]:
    try:
        from services.technical_analysis_service import fetch_ohlc_history

        hist = fetch_ohlc_history(ticker, period="2mo")
        if hist is None or hist.empty:
            return []
        tail = hist.tail(limit)
        return [
            {"open": float(r["Open"]), "high": float(r["High"]), "low": float(r["Low"]), "close": float(r["Close"])}
            for _, r in tail.iterrows()
            if all(v == v for v in (r["Open"], r["High"], r["Low"], r["Close"]))  # drop NaN rows
        ]
    except Exception:
        return []


def _ffprobe_duration(path: str) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "csv=p=0", path],
        capture_output=True, text=True, timeout=15,
    )
    try:
        return float(out.stdout.strip())
    except (ValueError, TypeError):
        return 3.0  # safe fallback slide length if ffprobe's own output is ever unparseable


def generate_daily_video(lang: str = "zh-HK", max_signals: int = 3,
                          aspect_ratio: str = _DEFAULT_ASPECT, theme: str = _DEFAULT_THEME) -> dict:
    """Real end-to-end render. Returns {"available": False, "message":
    ...} immediately if TTS or ffmpeg aren't configured -- never
    attempts a partial render. On success returns {"available": True,
    "path": ..., "duration_sec": ..., "slides_count": ..., "lang": ...,
    "aspect_ratio": ..., "theme": ..., "used_ai_script": bool}."""
    if not is_available():
        msg = "Video Engine unavailable: " + (
            "GOOGLE_TTS_API_KEY not set" if not tts_service.is_available() else "ffmpeg/ffprobe not found on PATH"
        )
        _log_generation("unavailable", msg)
        return {"available": False, "message": msg}

    lang = lang if lang in _SCRIPT else "en"
    script = _SCRIPT[lang]
    width, height = _ASPECT_RATIOS.get(aspect_ratio, _ASPECT_RATIOS[_DEFAULT_ASPECT])
    aspect_ratio = aspect_ratio if aspect_ratio in _ASPECT_RATIOS else _DEFAULT_ASPECT
    colors = _THEMES.get(theme, _THEMES[_DEFAULT_THEME])
    theme = theme if theme in _THEMES else _DEFAULT_THEME

    try:
        from api.market_pulse import _compute_free_signals

        cache = _compute_free_signals()
        signals = (cache.get("signals") or [])[:max_signals]
    except Exception as e:
        _log_generation("error", f"Failed to fetch signals: {e}")
        return {"available": False, "message": f"Failed to fetch today's signals: {e}"}

    if not signals:
        _log_generation("error", "No signals available today")
        return {"available": False, "message": "No signals available today"}

    for s in signals:
        s["_candles"] = _fetch_candles(s["ticker"])

    slides = [("intro", None)] + [("signal", s) for s in signals] + [("outro", None)]

    # Template narration is built first as the honest, always-available
    # fallback; the AI rewrite (if it succeeds and returns the right
    # number of lines) replaces it wholesale, never partially -- a mix
    # of AI-written and template lines would be a worse, inconsistent
    # result than picking one source cleanly.
    template_texts = []
    for kind, s in slides:
        if kind == "intro":
            template_texts.append(script["intro"])
        elif kind == "outro":
            template_texts.append(script["outro"])
        else:
            direction = (s.get("confluence_direction") or "neutral").lower()
            template_texts.append(script["signal"].format(
                ticker=s["ticker"],
                direction=script["direction_label"].get(direction, direction),
                confidence=s.get("confluence_confidence_pct", 0),
            ))

    ai_texts = _ai_rewrite_narration(signals, lang)
    used_ai_script = ai_texts is not None
    narration_texts = ai_texts if used_ai_script else template_texts

    workdir = tempfile.mkdtemp(prefix="xfl_video_")
    try:
        audio_paths = []
        for i, text in enumerate(narration_texts):
            tts_result = tts_service.synthesize(_build_ssml(text), lang=lang, ssml=True)
            if not tts_result.get("available"):
                _log_generation("error", f"TTS failed on slide {i}: {tts_result.get('message')}")
                return {"available": False, "message": f"TTS failed: {tts_result.get('message')}"}
            audio_path = os.path.join(workdir, f"audio_{i}.mp3")
            with open(audio_path, "wb") as f:
                f.write(tts_result["audio_bytes"])
            audio_paths.append(audio_path)

        durations = [_ffprobe_duration(p) for p in audio_paths]

        image_list_path = os.path.join(workdir, "images.txt")
        with open(image_list_path, "w") as f:
            for i, ((kind, s), dur) in enumerate(zip(slides, durations)):
                img = _render_slide(kind, s, lang, narration_texts[i], width, height, colors)
                img_path = os.path.join(workdir, f"slide_{i}.png")
                img.save(img_path)
                f.write(f"file '{img_path}'\nduration {dur}\n")
            # concat demuxer quirk: the last image's `duration` is ignored
            # unless the file is listed one more time afterward.
            f.write(f"file '{os.path.join(workdir, f'slide_{len(slides) - 1}.png')}'\n")

        silent_video_path = os.path.join(workdir, "silent.mp4")
        subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", image_list_path,
             "-vsync", "vfr", "-pix_fmt", "yuv420p", silent_video_path],
            capture_output=True, timeout=120, check=True,
        )

        narration_path = os.path.join(workdir, "narration.mp3")
        concat_inputs = []
        for p in audio_paths:
            concat_inputs += ["-i", p]
        n = len(audio_paths)
        filter_str = "".join(f"[{i}:a]" for i in range(n)) + f"concat=n={n}:v=0:a=1[out]"
        subprocess.run(
            ["ffmpeg", "-y", *concat_inputs, "-filter_complex", filter_str, "-map", "[out]", narration_path],
            capture_output=True, timeout=60, check=True,
        )

        os.makedirs(_OUTPUT_DIR, exist_ok=True)
        final_path = os.path.join(_OUTPUT_DIR, _OUTPUT_FILENAME)
        subprocess.run(
            ["ffmpeg", "-y", "-i", silent_video_path, "-i", narration_path,
             "-c:v", "copy", "-c:a", "aac", "-b:a", "128k", "-shortest", final_path],
            capture_output=True, timeout=60, check=True,
        )

        total_duration = sum(durations)
        _log_generation(
            "ok",
            f"Generated with {len(signals)} signals ({lang}, {aspect_ratio}, {theme} theme, "
            f"AI script: {'yes' if used_ai_script else 'no (template fallback)'})",
            total_duration, len(slides),
        )
        return {
            "available": True,
            "path": final_path,
            "duration_sec": round(total_duration, 1),
            "slides_count": len(slides),
            "lang": lang,
            "aspect_ratio": aspect_ratio,
            "theme": theme,
            "used_ai_script": used_ai_script,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
    except subprocess.CalledProcessError as e:
        err = (e.stderr or b"").decode("utf-8", errors="ignore")[-500:]
        _log_generation("error", f"ffmpeg failed: {err}")
        return {"available": False, "message": f"Video rendering failed: {err}"}
    except Exception as e:
        _log_generation("error", str(e))
        return {"available": False, "message": f"Video generation failed: {e}"}
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
