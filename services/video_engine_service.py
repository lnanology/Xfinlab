"""Growth OS Phase 7 (2026-08-04): AI Video Engine -- turns today's real
free signals (api/market_pulse.py's _compute_free_signals(), the exact
same data free-signals.html/the Telegram push/the email digest already
use) into a short narrated vertical video (1080x1920, TikTok/Shorts/
Reels-shaped) for distribution channels where a text post gets no
traction but a short video does.

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
  2. TTS each slide's line separately (services/tts_service.py) so each
     slide can be timed to its own narration clip's real duration.
  3. Render each slide as a 1080x1920 PNG: XFINLAB branding, ticker,
     direction, confidence, and a real candlestick strip.
  4. ffmpeg concat-demuxer the images (each held for its matching
     narration duration) into a silent video.
  5. ffmpeg filter_complex-concat the narration clips into one audio
     track, then mux it onto the silent video.

Storage: Railway's filesystem is NOT persisted across deploys/restarts
(litestream.yml only replicates xfinlab.db, never arbitrary files) --
this writes only ONE rolling file (generated_videos/daily_video_latest
.mp4), regenerated once a day, never treated as a permanent archive.
That's an accepted tradeoff for a daily marketing asset, not a defect;
if a durable archive is ever wanted, that's a separate follow-up
(uploading to real object storage), not something to fake here.

is_available() gates on BOTH services.tts_service.is_available() (needs
GOOGLE_TTS_API_KEY) AND the `ffmpeg`/`ffprobe` binaries actually being on
PATH (added via nixpacks.toml's nixPkgs for the Railway build) -- if
either is missing, every entrypoint here returns {"available": False,
"message": ...} instead of raising, so a misconfigured deploy degrades
this ONE optional feature instead of crashing anything else.
"""
import os
import shutil
import subprocess
import tempfile
from datetime import date, datetime, timezone
from typing import List, Optional

from PIL import Image, ImageDraw, ImageFont

from services import tts_service

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "xfinlab.db")
_OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "generated_videos")
_OUTPUT_FILENAME = "daily_video_latest.mp4"

_WIDTH, _HEIGHT = 1080, 1920
_BG_COLOR = (8, 12, 20)
_ACCENT = (0, 212, 255)
_GREEN = (34, 197, 94)
_RED = (239, 68, 68)
_MUTED = (148, 163, 184)
_WHITE = (226, 232, 240)

# 2026-08-04: narration copy kept in just 2 languages (zh-HK/en), same
# deliberately-narrower-than-the-47-language-site-convention scope
# decision content_repurpose_service.py's EN/ES social fan-out already
# established for backend-generated marketing copy.
_SCRIPT = {
    "zh-HK": {
        "intro": "XFINLAB 今日AI市場速覽。",
        "signal": "{ticker}，{direction}，信心度 {confidence} 巴仙。",
        "outro": "以上為技術面參考，並非投資建議。想睇更多，去 xfinlab.com。",
        "direction_label": {"bullish": "偏多", "bearish": "偏空", "neutral": "中性"},
    },
    "en": {
        "intro": "XFINLAB's daily AI market snapshot.",
        "signal": "{ticker}: {direction}, {confidence} percent confidence.",
        "outro": "This is technical reference only, not investment advice. More at xfinlab.com.",
        "direction_label": {"bullish": "bullish", "bearish": "bearish", "neutral": "neutral"},
    },
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
    -- never hidden)."""
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
    }


def _get_font(size: int) -> ImageFont.FreeTypeFont:
    # DejaVuSans is bundled with Pillow's own test fonts on most Linux
    # distros (and Railway's nixpacks Python image); fall back to
    # Pillow's built-in bitmap font if it's genuinely missing rather
    # than crashing the whole render over a cosmetic font choice.
    for path in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ):
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    return ImageFont.load_default()


def _render_slide(kind: str, signal: Optional[dict], lang: str) -> Image.Image:
    img = Image.new("RGB", (_WIDTH, _HEIGHT), _BG_COLOR)
    draw = ImageDraw.Draw(img)

    # Branding header, every slide.
    draw.text((60, 70), "XFINLAB", font=_get_font(64), fill=_ACCENT)
    draw.text((60, 150), "AI Market Signal", font=_get_font(32), fill=_MUTED)

    if kind == "intro":
        text = _SCRIPT[lang]["intro"]
        draw.text((60, 800), text, font=_get_font(56), fill=_WHITE)
    elif kind == "outro":
        text = _SCRIPT[lang]["outro"]
        # Wrap manually at a fixed char count -- no textwrap dependency
        # surprises, good enough for a short disclaimer line.
        import textwrap
        for i, line in enumerate(textwrap.wrap(text, width=18)):
            draw.text((60, 800 + i * 70), line, font=_get_font(48), fill=_WHITE)
    else:  # "signal"
        direction = (signal.get("confluence_direction") or "neutral").lower()
        color = _GREEN if direction == "bullish" else (_RED if direction == "bearish" else _MUTED)
        direction_label = _SCRIPT[lang]["direction_label"].get(direction, direction)

        draw.text((60, 260), signal["ticker"], font=_get_font(120), fill=_WHITE)
        draw.text((60, 400), signal.get("label", ""), font=_get_font(36), fill=_MUTED)
        draw.text((60, 470), direction_label.upper(), font=_get_font(56), fill=color)
        conf = signal.get("confluence_confidence_pct")
        if conf is not None:
            draw.text((60, 550), f"{conf}%", font=_get_font(90), fill=color)

        # Real candlestick strip from real OHLC data -- honesty per this
        # module's docstring: a genuine (if simplified) chart, not a
        # decorative placeholder.
        candles = signal.get("_candles") or []
        if candles:
            _draw_candles(draw, candles, x0=60, y0=750, w=_WIDTH - 120, h=500)

    # Disclaimer footer on every slide -- same standing site-wide rule
    # (see risk-warning.html / every AI-analysis page) that any signal-
    # like content carries a non-advice disclaimer.
    draw.text((60, _HEIGHT - 140), "技術面參考，並非投資建議 / Not investment advice",
              font=_get_font(24), fill=_MUTED)

    return img


def _draw_candles(draw: ImageDraw.ImageDraw, candles: List[dict], x0: int, y0: int, w: int, h: int):
    if not candles:
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
        color = _GREEN if c["close"] >= c["open"] else _RED
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


def generate_daily_video(lang: str = "zh-HK", max_signals: int = 3) -> dict:
    """Real end-to-end render. Returns {"available": False, "message":
    ...} immediately if TTS or ffmpeg aren't configured -- never
    attempts a partial render. On success returns {"available": True,
    "path": ..., "duration_sec": ..., "slides_count": ...}."""
    if not is_available():
        msg = "Video Engine unavailable: " + (
            "GOOGLE_TTS_API_KEY not set" if not tts_service.is_available() else "ffmpeg/ffprobe not found on PATH"
        )
        _log_generation("unavailable", msg)
        return {"available": False, "message": msg}

    lang = lang if lang in _SCRIPT else "en"
    script = _SCRIPT[lang]

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

    workdir = tempfile.mkdtemp(prefix="xfl_video_")
    try:
        narration_texts = []
        for kind, s in slides:
            if kind == "intro":
                narration_texts.append(script["intro"])
            elif kind == "outro":
                narration_texts.append(script["outro"])
            else:
                direction = (s.get("confluence_direction") or "neutral").lower()
                narration_texts.append(script["signal"].format(
                    ticker=s["ticker"],
                    direction=script["direction_label"].get(direction, direction),
                    confidence=s.get("confluence_confidence_pct", 0),
                ))

        audio_paths = []
        for i, text in enumerate(narration_texts):
            tts_result = tts_service.synthesize(text, lang=lang)
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
                img = _render_slide(kind, s, lang)
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
        _log_generation("ok", f"Generated with {len(signals)} signals", total_duration, len(slides))
        return {
            "available": True,
            "path": final_path,
            "duration_sec": round(total_duration, 1),
            "slides_count": len(slides),
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
