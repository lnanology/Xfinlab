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
        "footer": "技術面參考，並非投資建議",
    },
    "zh-CN": {
        "intro": "XFINLAB 今日AI市场速览。",
        "signal": "{ticker}，{direction}，信心度 {confidence} 百分比。",
        "outro": "以上为技术面参考，并非投资建议。想了解更多，请访问 xfinlab.com。",
        "direction_label": {"bullish": "偏多", "bearish": "偏空", "neutral": "中性"},
        "footer": "技术面参考，并非投资建议",
    },
    "zh-TW": {
        "intro": "XFINLAB 今日AI市場速覽。",
        "signal": "{ticker}，{direction}，信心度 {confidence} 百分比。",
        "outro": "以上為技術面參考，並非投資建議。想了解更多，請造訪 xfinlab.com。",
        "direction_label": {"bullish": "偏多", "bearish": "偏空", "neutral": "中性"},
        "footer": "技術面參考，並非投資建議",
    },
    "en": {
        "intro": "XFINLAB's daily AI market snapshot.",
        "signal": "{ticker}: {direction}, {confidence} percent confidence.",
        "outro": "This is technical reference only, not investment advice. More at xfinlab.com.",
        "direction_label": {"bullish": "bullish", "bearish": "bearish", "neutral": "neutral"},
        "footer": "Technical reference only, not investment advice",
    },
    "es": {
        "intro": "El resumen diario del mercado con IA de XFINLAB.",
        "signal": "{ticker}: {direction}, {confidence} por ciento de confianza.",
        "outro": "Esto es solo referencia técnica, no es asesoría de inversión. Más en xfinlab.com.",
        "direction_label": {"bullish": "alcista", "bearish": "bajista", "neutral": "neutral"},
        "footer": "Solo referencia técnica, no es asesoría de inversión",
    },
    "ja": {
        "intro": "XFINLABの本日のAI市場スナップショットです。",
        "signal": "{ticker}、{direction}、信頼度 {confidence} パーセント。",
        "outro": "これは技術的参考情報であり、投資助言ではありません。詳細は xfinlab.com へ。",
        "direction_label": {"bullish": "強気", "bearish": "弱気", "neutral": "中立"},
        "footer": "技術的参考情報であり、投資助言ではありません",
    },
    "ko": {
        "intro": "XFINLAB의 오늘의 AI 시장 스냅샷입니다.",
        "signal": "{ticker}, {direction}, 신뢰도 {confidence} 퍼센트.",
        "outro": "이것은 기술적 참고 자료일 뿐이며 투자 조언이 아닙니다. 자세한 내용은 xfinlab.com에서 확인하세요.",
        "direction_label": {"bullish": "강세", "bearish": "약세", "neutral": "중립"},
        "footer": "기술적 참고 자료이며 투자 조언이 아닙니다",
    },
    # 2026-08-04 second expansion (user request: pt/fr/de/hi/id/ar/ru/bn/ur).
    # Real Google TTS voices for all 9 confirmed in services/tts_service.py's
    # _VOICE_MAP (see that file's comment for the per-language verification
    # depth) -- these narration scripts only exist for languages that
    # actually have a working voice behind them.
    "pt": {
        "intro": "Resumo diário do mercado com IA da XFINLAB.",
        "signal": "{ticker}: {direction}, {confidence} por cento de confiança.",
        "outro": "Isto é apenas referência técnica, não é aconselhamento de investimento. Mais em xfinlab.com.",
        "direction_label": {"bullish": "otimista", "bearish": "pessimista", "neutral": "neutro"},
        "footer": "Apenas referência técnica, não é aconselhamento de investimento",
    },
    "fr": {
        "intro": "Le résumé quotidien du marché par l'IA de XFINLAB.",
        "signal": "{ticker} : {direction}, {confidence} pour cent de confiance.",
        "outro": "Ceci est uniquement une référence technique, pas un conseil en investissement. Plus sur xfinlab.com.",
        "direction_label": {"bullish": "haussier", "bearish": "baissier", "neutral": "neutre"},
        "footer": "Référence technique uniquement, pas un conseil en investissement",
    },
    "de": {
        "intro": "Der tägliche KI-Marktüberblick von XFINLAB.",
        "signal": "{ticker}: {direction}, {confidence} Prozent Konfidenz.",
        "outro": "Dies ist nur eine technische Referenz, keine Anlageberatung. Mehr auf xfinlab.com.",
        "direction_label": {"bullish": "bullisch", "bearish": "bärisch", "neutral": "neutral"},
        "footer": "Nur technische Referenz, keine Anlageberatung",
    },
    "hi": {
        "intro": "XFINLAB का आज का एआई मार्केट स्नैपशॉट।",
        "signal": "{ticker}: {direction}, {confidence} प्रतिशत विश्वास।",
        "outro": "यह केवल तकनीकी संदर्भ है, निवेश सलाह नहीं। अधिक जानकारी के लिए xfinlab.com पर जाएं।",
        "direction_label": {"bullish": "तेजी", "bearish": "मंदी", "neutral": "तटस्थ"},
        "footer": "केवल तकनीकी संदर्भ, निवेश सलाह नहीं",
    },
    "id": {
        "intro": "Ringkasan pasar harian berbasis AI dari XFINLAB.",
        "signal": "{ticker}: {direction}, tingkat keyakinan {confidence} persen.",
        "outro": "Ini hanya referensi teknis, bukan saran investasi. Info lebih lanjut di xfinlab.com.",
        "direction_label": {"bullish": "cenderung naik", "bearish": "cenderung turun", "neutral": "netral"},
        "footer": "Hanya referensi teknis, bukan saran investasi",
    },
    "ar": {
        "intro": "الملخص اليومي لسوق XFINLAB المدعوم بالذكاء الاصطناعي.",
        "signal": "{ticker}: {direction}، بثقة {confidence} بالمئة.",
        "outro": "هذا مرجع فني فقط، وليس نصيحة استثمارية. لمزيد من المعلومات، تفضل بزيارة xfinlab.com.",
        "direction_label": {"bullish": "صاعد", "bearish": "هابط", "neutral": "محايد"},
        "footer": "مرجع فني فقط، وليس نصيحة استثمارية",
    },
    "ru": {
        "intro": "Ежедневный обзор рынка от XFINLAB на основе ИИ.",
        "signal": "{ticker}: {direction}, уверенность {confidence} процентов.",
        "outro": "Это только техническая справка, а не инвестиционный совет. Подробнее на xfinlab.com.",
        "direction_label": {"bullish": "растущий", "bearish": "падающий", "neutral": "нейтральный"},
        "footer": "Только техническая справка, не инвестиционный совет",
    },
    "bn": {
        "intro": "XFINLAB-এর আজকের এআই মার্কেট স্ন্যাপশট।",
        "signal": "{ticker}: {direction}, আত্মবিশ্বাস {confidence} শতাংশ।",
        "outro": "এটি শুধুমাত্র প্রযুক্তিগত তথ্য, বিনিয়োগের পরামর্শ নয়। আরও জানতে xfinlab.com দেখুন।",
        "direction_label": {"bullish": "ঊর্ধ্বমুখী", "bearish": "নিম্নমুখী", "neutral": "নিরপেক্ষ"},
        "footer": "শুধুমাত্র প্রযুক্তিগত তথ্য, বিনিয়োগের পরামর্শ নয়",
    },
    "ur": {
        "intro": "XFINLAB کا آج کا اے آئی مارکیٹ خلاصہ۔",
        "signal": "{ticker}: {direction}, {confidence} فیصد اعتماد۔",
        "outro": "یہ صرف تکنیکی حوالہ ہے، سرمایہ کاری کا مشورہ نہیں۔ مزید معلومات کے لیے xfinlab.com ملاحظہ کریں۔",
        "direction_label": {"bullish": "تیزی", "bearish": "مندی", "neutral": "غیر جانبدار"},
        "footer": "صرف تکنیکی حوالہ، سرمایہ کاری کا مشورہ نہیں",
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
    "pt": "Portuguese (Brazilian)",
    "fr": "French",
    "de": "German",
    "hi": "Hindi",
    "id": "Indonesian",
    "ar": "Modern Standard Arabic",
    "ru": "Russian",
    "bn": "Bengali",
    "ur": "Urdu",
}

# 2026-08-04 fix (user-reported: video's on-screen direction word and
# sector/ticker label stayed Chinese regardless of the chosen narration
# language, e.g. a Japanese-language video still showing "偏多" and
# "能源板塊"). Root cause of the direction bug: api/market_pulse.py's
# _compute_free_signals() (the exact data this module renders) sets
# confluence_direction to the RAW Chinese literal from technical_
# analysis_service.py ("偏多"/"偏空"), never "bullish"/"bearish" -- but
# _render_slide()/generate_daily_video() below used to do
# `direction = signal["confluence_direction"].lower()` and then look
# that up in _SCRIPT[lang]["direction_label"], whose keys are the
# English words "bullish"/"bearish"/"neutral". "偏多".lower() is still
# "偏多" (no-op on CJK), so the lookup always missed and silently fell
# back to the untranslated raw Chinese via dict.get(direction, direction)
# -- on every language, not just Chinese. This table normalizes the raw
# Chinese (or already-English) value to the canonical bullish/bearish/
# neutral key _SCRIPT actually indexes by, so the lookup can succeed.
_DIRECTION_NORMALIZE = {
    "偏多": "bullish", "偏空": "bearish",
    "bullish": "bullish", "bearish": "bearish",
    "訊號分歧，中性": "neutral", "數據不足": "neutral", "neutral": "neutral",
}


def _normalize_direction(raw: Optional[str]) -> str:
    if not raw:
        return "neutral"
    return _DIRECTION_NORMALIZE.get(raw, raw.lower() if raw.isascii() else "neutral")


# Root cause of the sector/ticker label bug: signal["label"] comes from
# api/market_pulse.py's _PULSE_LABELS/_TICKER_LABELS dicts, which are
# Chinese-only (e.g. "XLE" -> "能源板塊") -- there's no English/other-
# language version at the source. Rather than inventing a second label
# dictionary to maintain, this reuses the EXACT SAME i18n keys services/
# telegram_push_service.py already established for this identical
# problem (its 2026-07-26 fix: "en/es Telegram channels were posting
# Chinese ticker names" -- see that file's _TICKER_LABEL_KEYS comment)
# -- those keys are real, human-translated across all 47 site languages
# in services/i18n.py, so every language this module supports gets a
# real translation, not a guess.
_LABEL_I18N_KEYS = {
    "標普500": "tl_spy500", "納指100": "tl_qqq100", "道瓊工業": "pulse3",
    "羅素2000小型股": "tl_iwm_smallcap", "科技板塊": "pulse5", "金融板塊": "pulse6",
    "能源板塊": "pulse7", "標普500期貨": "tl_es_futures", "原油期貨": "tl_cl_futures",
    "黃金期貨": "tl_gc_futures", "比特幣": "tl_btc", "以太幣": "tl_eth",
}
# services/i18n.py's zh-HK/zh-TW/zh-CN entries for these keys don't
# always exactly match market_pulse.py's raw literal (traditional vs
# simplified, wording drift over time) -- for the Chinese narration
# languages the raw label is already correct as-is, so skip the lookup
# entirely rather than risk swapping in a slightly different phrasing.
_ZH_LANGS = {"zh-HK", "zh-CN", "zh-TW", "zh"}


def _translate_label(raw_label: str, lang: str) -> str:
    if not raw_label or lang in _ZH_LANGS:
        return raw_label
    key = _LABEL_I18N_KEYS.get(raw_label)
    if not key:
        return raw_label
    try:
        from services.i18n import get_translations

        return get_translations(lang).get(key, raw_label)
    except Exception:
        return raw_label


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

# 2026-08-04 second expansion: ar/ur (Arabic script) and hi/bn (Devanagari/
# Bengali script) have no glyphs at all in NotoSansCJK or DejaVuSans, so
# without this those 4 languages would render as tofu boxes -- the exact
# same bug class the 2026-08-04 CJK fix above already fixed once for
# Chinese/Japanese/Korean. nixpacks.toml's aptPkgs now also installs
# fonts-noto-core + fonts-noto-unhinted (broad Noto script coverage,
# including Arabic/Devanagari/Bengali) alongside the existing fonts-noto-
# cjk. Rather than hardcoding exact file paths for these packages (their
# internal file naming isn't something this codebase controls or can
# verify in advance), _scan_fonts() below does a one-time recursive scan
# of the actual font directories at runtime and matches by keyword in the
# filename -- resilient to whatever the real installed file names turn
# out to be, same "never invent, always verify against the real thing"
# posture as every other part of this module.
_SCRIPT_FONT_KEYWORDS = {
    "ar": ("Arabic",), "ur": ("Arabic",),
    "hi": ("Devanagari",), "bn": ("Bengali",),
}
_font_dir_index: Optional[List[str]] = None


def _scan_fonts() -> List[str]:
    global _font_dir_index
    if _font_dir_index is not None:
        return _font_dir_index
    index = []
    for base in ("/usr/share/fonts", "/usr/local/share/fonts"):
        if not os.path.isdir(base):
            continue
        for root, _dirs, files in os.walk(base):
            for fn in files:
                if fn.lower().endswith((".ttf", ".ttc", ".otf")):
                    index.append(os.path.join(root, fn))
    _font_dir_index = index
    return index


def _find_script_font(lang: str) -> Optional[str]:
    keywords = _SCRIPT_FONT_KEYWORDS.get(lang)
    if not keywords:
        return None
    matches = [p for p in _scan_fonts() if all(k.lower() in os.path.basename(p).lower() for k in keywords)]
    if not matches:
        return None
    bold = [p for p in matches if "bold" in os.path.basename(p).lower()]
    return sorted(bold or matches)[0]


def _get_font(size: int, lang: Optional[str] = None) -> ImageFont.FreeTypeFont:
    size = max(int(size), 8)
    candidates = list(_FONT_CANDIDATES)
    script_font = _find_script_font(lang) if lang else None
    if script_font:
        candidates = [script_font] + candidates
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size, index=0)
            except Exception:
                pass
    return ImageFont.load_default()


# 2026-08-04: real XFINLAB logo mark (the same asset img/logo-mark-512.png
# already used site-wide for favicons/nav branding, see task #335/#337 --
# not a new/invented asset), composited onto every slide next to the
# "XFINLAB" wordmark and, larger, on the outro end-screen. RGBA with a
# transparent background so it sits cleanly on both the dark and light
# slide themes. Cached per requested pixel size since the same handful of
# sizes repeat across every slide in a render.
_LOGO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "img", "logo-mark-512.png")
_logo_cache: dict = {}


def _get_logo(size: int) -> Optional[Image.Image]:
    size = max(int(size), 1)
    if size in _logo_cache:
        return _logo_cache[size]
    if not os.path.exists(_LOGO_PATH):
        _logo_cache[size] = None
        return None
    try:
        logo = Image.open(_LOGO_PATH).convert("RGBA").resize((size, size), Image.LANCZOS)
    except Exception:
        logo = None
    _logo_cache[size] = logo
    return logo


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
        # 2026-08-04 fix: confluence_direction from _compute_free_signals()
        # is the raw Chinese literal ("偏多"/"偏空"), not the English word
        # -- normalize it so the AI prompt states the direction in
        # English (the language this prompt itself is written in),
        # rather than embedding a stray Chinese character the model would
        # have to guess the meaning of.
        direction = _normalize_direction(s.get("confluence_direction"))
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


def _text_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, fallback_per_char: float) -> float:
    """textbbox is the modern Pillow way to measure text width for manual
    centering/right-alignment (textsize was removed in recent Pillow) --
    wrapped so every call site below degrades to a rough estimate instead
    of crashing if a given font/text combination ever raises."""
    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        return bbox[2] - bbox[0]
    except Exception:
        return len(text) * fallback_per_char


def _render_slide(kind: str, signal: Optional[dict], lang: str, caption_text: str,
                   width: int, height: int, colors: dict) -> Image.Image:
    img = Image.new("RGB", (width, height), colors["bg"])
    draw = ImageDraw.Draw(img)
    script = _SCRIPT.get(lang, _SCRIPT["en"])

    pad_x = int(width * 0.055)
    header_font_size = int(height * 0.033)
    sub_font_size = int(height * 0.017)
    header_y = int(height * 0.036)

    # Branding header, every slide: logo mark + "XFINLAB" wordmark at
    # top-left (2026-08-04: user asked for the logo icon to appear before
    # the wordmark, not just plain text), "xfinlab.com" at top-right so
    # it's visible even on a muted/no-sound autoplay view.
    icon_size = header_font_size + sub_font_size + 6
    logo_icon = _get_logo(icon_size)
    text_x = pad_x
    if logo_icon:
        img.paste(logo_icon, (pad_x, header_y), logo_icon)
        text_x = pad_x + icon_size + int(width * 0.018)
    draw.text((text_x, header_y), "XFINLAB", font=_get_font(header_font_size, lang), fill=colors["accent"])
    draw.text((text_x, header_y + header_font_size + 6), "AI Market Signal",
              font=_get_font(sub_font_size, lang), fill=colors["muted"])
    header_bottom = header_y + header_font_size + sub_font_size + int(height * 0.03)

    url_font = _get_font(sub_font_size, lang)
    url_w = _text_width(draw, "xfinlab.com", url_font, sub_font_size * 0.6)
    draw.text((width - pad_x - url_w, header_y + 2), "xfinlab.com", font=url_font, fill=colors["muted"])

    if kind == "intro":
        for i, line in enumerate(textwrap.wrap(caption_text, width=max(10, width // 26))):
            draw.text((pad_x, int(height * 0.42) + i * int(height * 0.037)), line,
                      font=_get_font(int(height * 0.032), lang), fill=colors["fg"])
    elif kind == "outro":
        for i, line in enumerate(textwrap.wrap(caption_text, width=max(10, width // 26))):
            draw.text((pad_x, int(height * 0.34) + i * int(height * 0.033)), line,
                      font=_get_font(int(height * 0.027), lang), fill=colors["fg"])

        # Prominent end-screen callout (2026-08-04: user asked for the
        # closing slide to show a big logo + xfinlab.com, not just the
        # small persistent header mark) -- centered, below the spoken
        # outro line above.
        end_logo_size = int(height * 0.16)
        end_logo = _get_logo(end_logo_size)
        end_y = int(height * 0.62)
        if end_logo:
            img.paste(end_logo, (width // 2 - end_logo_size // 2, end_y), end_logo)
            end_y += end_logo_size + int(height * 0.02)
        wordmark_font = _get_font(int(height * 0.045), lang)
        wm_w = _text_width(draw, "XFINLAB", wordmark_font, height * 0.03)
        draw.text((width // 2 - wm_w / 2, end_y), "XFINLAB", font=wordmark_font, fill=colors["accent"])
        end_y += int(height * 0.055)
        end_url_font = _get_font(int(height * 0.024), lang)
        end_url_w = _text_width(draw, "xfinlab.com", end_url_font, height * 0.016)
        draw.text((width // 2 - end_url_w / 2, end_y), "xfinlab.com", font=end_url_font, fill=colors["muted"])
    elif kind == "custom":
        # 2026-08-09 (admin chat-to-video feature): body slides for an
        # arbitrary admin-supplied topic, with no ticker/OHLC data to
        # render -- same simple vertically-centered wrapped-text layout as
        # "intro" above, reused rather than duplicated since there's no
        # per-slide structured data to lay out beyond the caption itself.
        lines = textwrap.wrap(caption_text, width=max(10, width // 24))
        line_h = int(height * 0.037)
        start_y = int(height * 0.5) - (len(lines) * line_h) // 2
        for i, line in enumerate(lines):
            draw.text((pad_x, start_y + i * line_h), line,
                      font=_get_font(int(height * 0.032), lang), fill=colors["fg"])
    elif kind == "chart":
        # 2026-08-09 (admin chat-to-video feature): custom-topic slide that
        # DOES have a real ticker -- e.g. admin typed "make a video about
        # NVDA earnings". Reuses the same real-OHLC candlestick renderer as
        # the "signal" branch below (_draw_candles, fed by _fetch_candles's
        # genuine Alpaca/yfinance data), but without a direction/confidence
        # call, since a custom-topic video isn't making a confluence-engine
        # signal claim -- it's just grounding the AI narration in an actual
        # price chart instead of a blank slide, same anti-fabrication
        # discipline as the rest of this module.
        ticker = (signal or {}).get("ticker", "")
        y = header_bottom
        draw.text((pad_x, y), ticker, font=_get_font(int(height * 0.062), lang), fill=colors["fg"])
        y += int(height * 0.09)

        candles = (signal or {}).get("_candles") or []
        candle_bottom = height - int(height * 0.2)
        if candles and candle_bottom > y:
            _draw_candles(draw, candles, x0=pad_x, y0=y, w=width - 2 * pad_x, h=candle_bottom - y, colors=colors)

        cap_y = height - int(height * 0.145)
        for i, line in enumerate(textwrap.wrap(caption_text, width=max(10, width // 24))[:3]):
            draw.text((pad_x, cap_y + i * int(height * 0.025)), line,
                      font=_get_font(int(height * 0.021), lang), fill=colors["fg"])
    else:  # "signal"
        direction = _normalize_direction(signal.get("confluence_direction"))
        color = colors["green"] if direction == "bullish" else (colors["red"] if direction == "bearish" else colors["muted"])
        direction_label = script["direction_label"].get(direction, direction)
        label = _translate_label(signal.get("label", ""), lang)

        y = header_bottom
        draw.text((pad_x, y), signal["ticker"], font=_get_font(int(height * 0.062), lang), fill=colors["fg"])
        y += int(height * 0.075)
        draw.text((pad_x, y), label, font=_get_font(int(height * 0.019), lang), fill=colors["muted"])
        y += int(height * 0.035)
        draw.text((pad_x, y), direction_label.upper(), font=_get_font(int(height * 0.029), lang), fill=color)
        y += int(height * 0.042)
        conf = signal.get("confluence_confidence_pct")
        if conf is not None:
            draw.text((pad_x, y), f"{conf}%", font=_get_font(int(height * 0.047), lang), fill=color)
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
                      font=_get_font(int(height * 0.021), lang), fill=colors["fg"])

    # Disclaimer footer on every slide -- same standing site-wide rule
    # (see risk-warning.html / every AI-analysis page) that any signal-
    # like content carries a non-advice disclaimer. 2026-08-04 fix: this
    # used to be a hardcoded "技術面參考，並非投資建議 / Not investment
    # advice" literal regardless of narration language -- now pulled from
    # _SCRIPT[lang]["footer"], translated for real.
    footer_text = script.get("footer", "Technical reference only, not investment advice")
    draw.text((pad_x, height - int(height * 0.073)), footer_text,
              font=_get_font(int(height * 0.0125), lang), fill=colors["muted"])

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
            # 2026-08-04 fix: same raw-Chinese-vs-English-key mismatch as
            # _render_slide()/_ai_rewrite_narration() above -- confluence_
            # direction is "偏多"/"偏空" from the source data, not
            # "bullish"/"bearish", so this lookup used to silently miss on
            # every non-Chinese language and speak the raw Chinese word.
            direction = _normalize_direction(s.get("confluence_direction"))
            template_texts.append(script["signal"].format(
                ticker=s["ticker"],
                direction=script["direction_label"].get(direction, direction),
                confidence=s.get("confluence_confidence_pct", 0),
            ))

    ai_texts = _ai_rewrite_narration(signals, lang)
    used_ai_script = ai_texts is not None
    narration_texts = ai_texts if used_ai_script else template_texts

    result = _render_video_pipeline(
        slides, narration_texts, lang, aspect_ratio, width, height, colors,
        log_note=f"Generated with {len(signals)} signals ({lang}, {aspect_ratio}, {theme} theme, "
                  f"AI script: {'yes' if used_ai_script else 'no (template fallback)'})",
    )
    if result.get("available"):
        result["theme"] = theme
        result["used_ai_script"] = used_ai_script
    return result


def _render_video_pipeline(slides: list, narration_texts: List[str], lang: str, aspect_ratio: str,
                            width: int, height: int, colors: dict, log_note: str) -> dict:
    """Shared TTS -> slide-render -> ffmpeg-assemble pipeline used by both
    generate_daily_video() (fixed today's-signals content) and
    generate_custom_video() (arbitrary admin-chat-requested content) --
    extracted 2026-08-09 so the two content sources don't duplicate this
    ~80-line ffmpeg/TTS assembly logic. `slides` is a list of (kind,
    payload) tuples matching len(narration_texts) 1:1, exactly as
    _render_slide() expects."""
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
        _log_generation("ok", log_note, total_duration, len(slides))
        return {
            "available": True,
            "path": final_path,
            "duration_sec": round(total_duration, 1),
            "slides_count": len(slides),
            "lang": lang,
            "aspect_ratio": aspect_ratio,
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


_VALID_LANGS = None  # set lazily below to avoid a forward-reference to _SCRIPT


def _ai_write_custom_script(topic: str, num_slides: int, lang: str) -> Optional[List[str]]:
    """2026-08-09 (admin chat-to-video feature): asks the site's AI router
    to write narration for an ADMIN-SUPPLIED arbitrary topic, not today's
    real signals -- so unlike _ai_rewrite_narration() above, there is no
    real-data fact block to ground the output in. Guardrails here matter
    more, not less: the prompt explicitly forbids inventing specific
    numbers (prices/percentages/returns) unless the admin's own topic text
    supplied them, same "never fabricate a figure" rule this codebase has
    enforced since the MasterPipeline/Stress-Lab fabricated-number cleanup
    (tasks #226/#230/#272). Returns None on any failure -- caller must
    treat that as "cannot generate this custom video", there is no
    template fallback for an arbitrary topic the way the daily video has."""
    try:
        from ai.ai_router import get_ai_response
    except Exception:
        return None

    lang_name = _AI_LANG_NAMES.get(lang, "English")
    body_lines = max(1, num_slides - 2)

    prompt = (
        f"You are writing a SHORT spoken video-narration script in {lang_name} for XFINLAB, a "
        f"financial data/research platform. Output EXACTLY {num_slides} lines, one sentence per "
        f"line, no numbering, no markdown, no quotation marks:\n"
        f"Line 1: a 1-sentence intro naming XFINLAB and the topic below.\n"
        f"Lines 2 through {num_slides - 1}: {body_lines} sentence(s) of general, factual "
        f"commentary on the topic, professional financial-news tone. Do NOT invent specific "
        f"prices, percentages, dates, or return figures that are not explicitly given in the "
        f"topic text -- describe concepts, context, and publicly known facts only.\n"
        f"Line {num_slides}: a 1-sentence closing disclaimer that this is general information "
        f"only, not investment advice, mentioning xfinlab.com.\n\n"
        f"Topic (as requested by the XFINLAB team):\n{topic}\n\n"
        f"Output ONLY the {num_slides} lines of narration text, nothing else."
    )

    try:
        response = get_ai_response(prompt, max_tokens=500, reasoning_effort="low")
    except Exception:
        return None
    if not response:
        return None

    lines = [ln.strip(" \t\"'") for ln in response.strip().split("\n") if ln.strip()]
    if len(lines) != num_slides:
        return None
    return lines


def parse_video_chat_request(message: str) -> dict:
    """2026-08-09: turns one free-text admin chat message (e.g. "make a
    video about NVDA earnings, in Spanish, square format") into
    {"topic": ..., "lang": ..., "aspect_ratio": ..., "theme": ...}.
    Deliberately simple keyword matching, not another AI call -- this is
    an internal admin tool where a wrong guess just means the admin picks
    the right dropdown value instead, not worth a second LLM round-trip
    (and a second point of failure) for. `topic` is always the full
    original message verbatim, since the AI script-writer in
    _ai_write_custom_script() needs the complete request anyway, including
    whatever language/format words a keyword scan might strip out."""
    text = (message or "").strip()
    lower = text.lower()

    lang = "zh-HK"
    for code, name in _AI_LANG_NAMES.items():
        if code.lower() in lower or name.lower() in lower:
            lang = code
            break

    aspect_ratio = _DEFAULT_ASPECT
    if any(k in lower for k in ("square", "1:1", "instagram", "ig feed")):
        aspect_ratio = "1:1"
    elif any(k in lower for k in ("16:9", "landscape", "youtube", "widescreen")):
        aspect_ratio = "16:9"
    elif any(k in lower for k in ("9:16", "vertical", "shorts", "reels", "tiktok")):
        aspect_ratio = "9:16"

    theme = _DEFAULT_THEME
    if "light theme" in lower or "light mode" in lower or " light " in f" {lower} ":
        theme = "light"
    elif "dark theme" in lower or "dark mode" in lower:
        theme = "dark"

    return {"topic": text, "lang": lang, "aspect_ratio": aspect_ratio, "theme": theme}


def generate_custom_video(prompt_text: str, num_slides: int = 4, lang_override: str = None) -> dict:
    """2026-08-09 (admin chat-to-video feature, requested as "Video Engine
    可以加個CHAT更彈性做任何影片嗎"): admin-only, free-text-driven video
    generation, separate from generate_daily_video()'s fixed
    today's-signals format. Same availability/TTS/ffmpeg gating as
    generate_daily_video() -- reuses is_available() implicitly via
    _render_video_pipeline's TTS calls failing gracefully if unconfigured.
    num_slides is capped to a small range so one chat message can't
    request an unreasonably long (expensive) render.

    2026-08-13 (explicit language dropdown for the chat panel, matching
    the fixed Generate Now panel's videoLangSelect): lang_override, if
    given and a recognized code, takes priority over
    parse_video_chat_request()'s keyword-guessed language -- lets the
    admin just pick a dropdown instead of having to phrase the prompt so
    the guesser catches it (e.g. non-English topic text that doesn't
    literally name its own language)."""
    if not is_available():
        msg = "Video Engine unavailable: " + (
            "GOOGLE_TTS_API_KEY not set" if not tts_service.is_available() else "ffmpeg/ffprobe not found on PATH"
        )
        _log_generation("unavailable", msg)
        return {"available": False, "message": msg}

    if not (prompt_text or "").strip():
        return {"available": False, "message": "Empty request -- describe what the video should be about."}

    num_slides = max(3, min(8, num_slides))  # intro + at least 1 body + outro, capped at 8 total

    parsed = parse_video_chat_request(prompt_text)
    if lang_override and lang_override in _SCRIPT:
        lang = lang_override
    else:
        lang = parsed["lang"] if parsed["lang"] in _SCRIPT else "en"
    aspect_ratio = parsed["aspect_ratio"] if parsed["aspect_ratio"] in _ASPECT_RATIOS else _DEFAULT_ASPECT
    theme = parsed["theme"] if parsed["theme"] in _THEMES else _DEFAULT_THEME
    width, height = _ASPECT_RATIOS[aspect_ratio]
    colors = _THEMES[theme]

    narration_texts = _ai_write_custom_script(parsed["topic"], num_slides, lang)
    if narration_texts is None:
        _log_generation("error", f"AI script-writer failed for custom topic: {parsed['topic'][:80]!r}")
        return {"available": False, "message": "AI could not write a script for this request -- try rephrasing it."}

    # 2026-08-09: if the admin's topic names a real ticker (e.g. "make a
    # video about NVDA earnings"), ground the first body slide in an actual
    # candlestick chart instead of plain text -- same real-OHLC renderer
    # ("chart" kind added to _render_slide) that the daily-signals video
    # already uses. Detection reuses intent_router_service's AI-assisted
    # classifier (handles conversational/non-English topic text, e.g.
    # "講吓比特幣", not just literal "NVDA" tokens) rather than duplicating
    # ticker-parsing logic here. Best-effort: any failure here (AI router
    # down, no candle data returned) just means plain "custom" text slides,
    # never blocks the video -- a chart is a bonus, not a requirement.
    chart_ticker = None
    chart_candles = []
    try:
        from services.intent_router_service import classify_ai
        classification = classify_ai(parsed["topic"])
        candidate = (classification or {}).get("ticker")
        if candidate:
            candidate = str(candidate).strip().upper()
            candles = _fetch_candles(candidate, limit=20)
            if candles:
                chart_ticker, chart_candles = candidate, candles
    except Exception:
        chart_ticker, chart_candles = None, []

    body_kinds = ["custom"] * (num_slides - 2)
    if chart_ticker and body_kinds:
        body_kinds[0] = "chart"
    body_payloads = [{"ticker": chart_ticker, "_candles": chart_candles} if k == "chart" else None for k in body_kinds]
    slides = [("intro", None)] + list(zip(body_kinds, body_payloads)) + [("outro", None)]

    result = _render_video_pipeline(
        slides, narration_texts, lang, aspect_ratio, width, height, colors,
        log_note=f"Custom video: {parsed['topic'][:80]!r} ({lang}, {aspect_ratio}, {theme} theme)",
    )
    if result.get("available"):
        result["theme"] = theme
        result["topic"] = parsed["topic"]
        if chart_ticker:
            result["chart_ticker"] = chart_ticker
    return result
