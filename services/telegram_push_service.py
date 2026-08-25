"""
Telegram channel auto-push (daily top-opportunity signals).

Uses the plain Telegram Bot API (`sendMessage`) via a direct HTTPS POST --
NOT the python-telegram-bot polling app in growth/telegram_bot.py, which is
a separate long-running process for interactive /commands. This module is a
one-shot "push a message" helper meant to be called from the existing daily
APScheduler job (see api/market_pulse.py's _notify_free_signals_ready).

Reuses the same TELEGRAM_BOT_TOKEN already loaded by growth/telegram_bot.py,
plus three per-language channel IDs already present in .env:
  TELEGRAM_CHANNEL_ID     -- English channel (t.me/xfinlab_daily)
  TELEGRAM_ZH_CHANNEL_ID  -- Chinese channel (t.me/xfinlab_zh)
  TELEGRAM_ES_CHANNEL_ID  -- Spanish channel (t.me/xfinlab_es)

Best-effort only: every function here swallows its own exceptions so a
Telegram outage/misconfiguration never breaks the free-signals cache
refresh it piggybacks on (same philosophy as services/push_service.py).
"""
import os
from typing import Optional

import requests

from services.i18n import get_translations

TELEGRAM_API_BASE = "https://api.telegram.org"

# 2026-07-26 fix: the en/es Telegram channels were posting Chinese ticker
# names and Chinese direction words ("偏多"/"偏空") because
# api/market_pulse.py's _TICKER_LABELS/_ASSET_CLASS_LABELS dicts (and
# technical_analysis_service.py's confluence "direction" field) are
# Chinese-only -- _fmt_signal_line() below used to print those raw values
# straight into every channel's message regardless of language.
#
# Rather than inventing new EN/ES label dictionaries (a second source of
# truth to keep in sync), this reuses the EXACT SAME i18n keys the
# homepage's own JS translation helpers (trPulseLabel()/trDirection() in
# index.html) already map these identical raw Chinese strings to -- those
# keys are already real, human-translated across all 46 languages
# (services/i18n.py), so "es"/"en" here get the same correct text the
# website itself would show, not a fresh guess.
_TICKER_LABEL_KEYS = {
    "標普500": "tl_spy500", "納指100": "tl_qqq100", "道瓊工業": "pulse3",
    "羅素2000小型股": "tl_iwm_smallcap", "科技板塊": "pulse5", "金融板塊": "pulse6",
    "能源板塊": "pulse7", "標普500期貨": "tl_es_futures", "原油期貨": "tl_cl_futures",
    "黃金期貨": "tl_gc_futures", "比特幣": "tl_btc", "以太幣": "tl_eth",
}
_ASSET_CLASS_LABEL_KEYS = {
    "股票": "topopp_class_stock", "期貨": "topopp_class_futures", "加密貨幣": "topopp_class_crypto",
}
# sig["label"] is normally a ticker name (_TICKER_LABEL_KEYS), but
# _fmt_signal_line falls back to sig["asset_class_label"] if "label" is
# ever missing -- merge both maps so that lookup works either way.
_LABEL_KEYS = {**_TICKER_LABEL_KEYS, **_ASSET_CLASS_LABEL_KEYS}
_DIRECTION_KEYS = {
    "偏多": "idx_dir_bull", "偏空": "idx_dir_bear",
    "訊號分歧，中性": "idx_dir_neutral", "數據不足": "idx_dir_insufficient",
}


def _tr(raw: str, key_map: dict, lang: str) -> str:
    """Translate a raw Chinese label/direction string for the given
    channel language via services/i18n.py -- falls back to the raw
    Chinese untouched if lang=="zh" (correct as-is) or if this particular
    string has no mapped key (never crashes on an unrecognized value)."""
    if lang == "zh" or not raw:
        return raw
    key = key_map.get(raw)
    if not key:
        return raw
    return get_translations(lang).get(key, raw)


def _bot_token() -> str:
    return os.getenv("TELEGRAM_BOT_TOKEN", "")


def send_telegram_message(chat_id: str, text: str, parse_mode: str = "Markdown") -> bool:
    """Send one message to one chat/channel. Returns True on success,
    False on any failure (never raises)."""
    token = _bot_token()
    if not token or not chat_id:
        return False
    try:
        res = requests.post(
            f"{TELEGRAM_API_BASE}/bot{token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": parse_mode,
                "disable_web_page_preview": True,
            },
            timeout=10,
        )
        return res.status_code == 200
    except Exception:
        return False


# 2026-08-06 (Positioning batch, task #666): rewrote this from a
# single-ticker "🚀 BUY NVDA"-style signal list into a multi-point
# aggregated research brief, per the corrected Paddle-compliance read:
# Bloomberg's "Five Things You Need to Know" and Morningstar's daily
# note are automatic daily pushes too (industry-standard, not itself
# risky) -- what actually distinguishes a regulated "signal service"
# is CONTENT FORMAT (one ticker + a direct buy/sell command) vs. a
# section-headed brief with a Research Score + bias per line, an
# educational note, and an explicit disclaimer. This keeps the exact
# same underlying data (still the real confluence engine output, no
# new fabricated fields) -- only the framing/labels/section structure
# changed, so it stays honest about what it actually is: a formula-
# derived reference score, not a personalized trade instruction.
def _fmt_signal_line(sig: dict, lang: str) -> str:
    ticker = sig.get("ticker", "?")
    raw_label = sig.get("label") or sig.get("asset_class_label") or ""
    raw_direction = sig.get("confluence_direction", "")
    conf = sig.get("confluence_confidence_pct")
    conf_str = f"{conf}%" if conf is not None else "N/A"
    # 2026-07-26 fix: match against the RAW Chinese direction literals
    # ("偏多"/"偏空") that technical_analysis_service.py's confluence
    # engine actually returns -- the old check compared against English
    # words ("bull"/"bullish"/...) that this field never contains, so
    # dir_emoji always fell through to the neutral "⚪" regardless of the
    # real direction, in every channel including zh.
    dir_emoji = "🟢" if raw_direction == "偏多" else ("🔴" if raw_direction == "偏空" else "⚪")
    label = _tr(raw_label, _LABEL_KEYS, lang)
    direction = _tr(raw_direction, _DIRECTION_KEYS, lang)
    score_word = {"zh": "研究評分", "es": "Puntuación"}.get(lang, "Research Score")
    return f"{dir_emoji} *{ticker}* {label} — {score_word} {conf_str} ({direction})"


_WATCHLIST_HEADER = {
    "en": "📋 *Today's Research Watchlist*",
    "zh": "📋 *今日研究關注清單*",
    "es": "📋 *Lista de Investigación de Hoy*",
}
_INSIGHT_HEADER = {
    "en": "💡 *Research Insight*",
    "zh": "💡 *研究洞察*",
    "es": "💡 *Perspectiva de Investigación*",
}
_NO_SIGNALS = {
    "en": "No standout research items today.",
    "zh": "今日暫無突出研究項目。",
    "es": "Hoy no hay elementos de investigación destacados.",
}
_INSIGHT_TEMPLATE = {
    "en": "Today's highest-confidence read is {ticker} ({label}) at {conf}% via XFINLAB's multi-factor confluence model (trend + risk + news sentiment). This reflects current data patterns, not a guarantee of future price direction.",
    "zh": "今日信心度最高嘅係 {ticker}（{label}），透過XFINLAB多因子綜合模型（趨勢+風險+新聞情緒）得出 {conf}%。呢個反映現時數據形態，並非對未來走勢嘅保證。",
    "es": "La lectura de mayor confianza hoy es {ticker} ({label}) con {conf}% según el modelo multifactorial de XFINLAB (tendencia + riesgo + sentimiento de noticias). Esto refleja patrones de datos actuales, no una garantía de la dirección futura del precio.",
}
_DISCLAIMER = {
    "en": "⚠️ Research information only. Not investment advice. Final decisions remain with the investor.",
    "zh": "⚠️ 僅供研究參考，不構成投資建議。最終投資決定權在於閣下本人。",
    "es": "⚠️ Solo información de investigación. No es asesoría de inversión. La decisión final es del inversor.",
}
_FULL_RESEARCH_LABEL = {"en": "Full research", "zh": "完整研究", "es": "Investigación completa"}


def _build_message(cache: dict, lang: str) -> str:
    signals = (cache.get("signals") or [])[:5]
    date_str = cache.get("date", "")
    lines = [_fmt_signal_line(s, lang) for s in signals]
    body = "\n".join(lines) if lines else _NO_SIGNALS.get(lang, _NO_SIGNALS["en"])

    insight = ""
    if signals:
        top = max(signals, key=lambda s: s.get("confluence_confidence_pct") or 0)
        top_label = _tr(top.get("label") or top.get("asset_class_label") or "", _LABEL_KEYS, lang)
        top_conf = top.get("confluence_confidence_pct")
        if top_conf is not None:
            insight = _INSIGHT_TEMPLATE.get(lang, _INSIGHT_TEMPLATE["en"]).format(
                ticker=top.get("ticker", "?"), label=top_label, conf=top_conf
            )

    title = {"zh": "XFINLAB 每日市場情報", "es": "Inteligencia de Mercado Diaria XFINLAB"}.get(
        lang, "XFINLAB Daily Market Intelligence"
    )
    header = f"📊 *{title}* — {date_str}\n\n"
    sections = [f"{_WATCHLIST_HEADER.get(lang, _WATCHLIST_HEADER['en'])}\n{body}"]
    if insight:
        sections.append(f"{_INSIGHT_HEADER.get(lang, _INSIGHT_HEADER['en'])}\n{insight}")

    full_research = _FULL_RESEARCH_LABEL.get(lang, _FULL_RESEARCH_LABEL["en"])
    footer = (
        f"\n\n{full_research}: https://www.xfinlab.com/market-brief.html"
        f"\n{_DISCLAIMER.get(lang, _DISCLAIMER['en'])}"
    )

    return header + "\n\n".join(sections) + footer


# 2026-08-25: daily research-card auto-post. AJ asked for a daily TG post
# = "one ticker's AI research screenshot + your take". Two ways to make
# the "screenshot" were on the table: a real headless-browser screenshot
# of ai-analysis.html (would need Chromium added to the Railway build --
# bigger image, slower/flakier deploys, real RAM risk since this is a
# single-process app where a browser crash could take the whole API down
# with it, and this exact approach already failed in the dev sandbox from
# missing system libs) vs. a Pillow-drawn research card using the same
# real numbers (server-side, no new dependency, no Railway config change,
# near-zero resource cost, can't crash anything else). AJ picked the
# Pillow card. Reuses the SAME top-signal selection _build_message()
# above already does (max confluence_confidence_pct) so "today's Top
# Opportunity" can't drift between the text push and the card, and reuses
# services/video_engine_service.py's font/logo helpers (_get_font,
# _get_logo, _text_width) instead of a second font-discovery
# implementation -- same "one source of truth" posture as the _tr()
# label/direction lookups above.
_CARD_SIZE = (1200, 630)
_CARD_BG = (8, 12, 20)
_CARD_PANEL = (13, 21, 37)
_CARD_ACCENT = (249, 115, 22)
_CARD_TEXT = (226, 232, 240)
_CARD_MUTED = (100, 116, 139)
_CARD_BULL = (34, 197, 94)
_CARD_BEAR = (239, 68, 68)
_CARD_NEUTRAL = (100, 116, 139)

_CARD_HEADER_LABEL = {
    "en": "XFINLAB Daily Market Intelligence",
    "zh": "XFINLAB 每日市場情報",
    "es": "Inteligencia de Mercado Diaria XFINLAB",
}
_CARD_SCORE_LABEL = {"en": "Research Score", "zh": "研究評分", "es": "Puntuación de Investigación"}
_CARD_METHOD_LINE = {
    "en": "Multi-factor confluence model -- trend + risk + news sentiment",
    "zh": "多因子綜合模型 —— 趨勢 + 風險 + 新聞情緒",
    "es": "Modelo multifactorial -- tendencia + riesgo + sentimiento de noticias",
}
_CARD_DIRECTION_WORD = {
    "偏多": {"en": "Bullish", "zh": "偏多", "es": "Alcista"},
    "偏空": {"en": "Bearish", "zh": "偏空", "es": "Bajista"},
    "訊號分歧，中性": {"en": "Neutral", "zh": "中性", "es": "Neutral"},
    "數據不足": {"en": "Insufficient data", "zh": "數據不足", "es": "Datos insuficientes"},
}
_CARD_DISCLAIMER_SHORT = {
    "en": "Research information only. Not investment advice.",
    "zh": "僅供研究參考，不構成投資建議。",
    "es": "Solo información de investigación. No es asesoría de inversión.",
}


def _pick_top_signal(cache: dict) -> Optional[dict]:
    """Same selection _build_message() above uses for its insight line:
    the highest-confidence signal in today's cache. Factored out so the
    card generator and the text push can never pick two different
    tickers for the same day."""
    signals = cache.get("signals") or []
    if not signals:
        return None
    return max(signals, key=lambda s: s.get("confluence_confidence_pct") or 0)


def generate_research_card(sig: dict, lang: str, date_str: str) -> Optional[bytes]:
    """Renders one 1200x630 PNG research card for a single signal --
    ticker, direction, confidence/research score, methodology line, date,
    disclaimer -- all real values already computed by the confluence
    engine (same data _fmt_signal_line()/_INSIGHT_TEMPLATE above already
    show in the text push), nothing fabricated for the image. Returns
    None on any rendering failure (missing Pillow, missing font, bad
    input) rather than raising -- callers treat a missing card as
    "skip the photo send, text push already went out" not a hard error."""
    try:
        from PIL import Image, ImageDraw
        from services.video_engine_service import _get_font, _get_logo, _text_width
    except Exception:
        return None

    try:
        ticker = sig.get("ticker", "?")
        raw_label = sig.get("label") or sig.get("asset_class_label") or ""
        raw_direction = sig.get("confluence_direction", "")
        label = _tr(raw_label, _LABEL_KEYS, lang)
        direction_word = _CARD_DIRECTION_WORD.get(raw_direction, {}).get(lang, raw_direction or "--")
        dir_color = _CARD_BULL if raw_direction == "偏多" else (_CARD_BEAR if raw_direction == "偏空" else _CARD_NEUTRAL)
        conf = sig.get("confluence_confidence_pct")
        conf_str = f"{conf}%" if conf is not None else "N/A"

        w, h = _CARD_SIZE
        img = Image.new("RGB", (w, h), _CARD_BG)
        draw = ImageDraw.Draw(img)

        pad = 56
        draw.rounded_rectangle([pad, pad, w - pad, h - pad], radius=24, fill=_CARD_PANEL, outline=(30, 41, 59), width=2)

        # Header: logo + wordmark (left), date (right)
        logo = _get_logo(48)
        header_y = pad + 32
        text_x = pad + 32
        if logo is not None:
            img.paste(logo, (pad + 32, header_y), logo)
            text_x = pad + 32 + 48 + 16
        f_word = _get_font(30, lang)
        draw.text((text_x, header_y + 6), "XFINLAB", font=f_word, fill=_CARD_TEXT)
        f_small = _get_font(20, lang)
        header_label = _CARD_HEADER_LABEL.get(lang, _CARD_HEADER_LABEL["en"])
        draw.text((text_x, header_y + 42), header_label, font=f_small, fill=_CARD_MUTED)
        date_w = _text_width(draw, date_str, f_small, 11)
        draw.text((w - pad - 32 - date_w, header_y + 12), date_str, font=f_small, fill=_CARD_MUTED)

        # Divider
        line_y = header_y + 88
        draw.line([(pad + 32, line_y), (w - pad - 32, line_y)], fill=(30, 41, 59), width=2)

        # Ticker + label (left column)
        f_ticker = _get_font(96, lang)
        ticker_y = line_y + 48
        draw.text((pad + 32, ticker_y), ticker, font=f_ticker, fill=_CARD_TEXT)
        f_label = _get_font(26, lang)
        draw.text((pad + 32, ticker_y + 108), label, font=f_label, fill=_CARD_MUTED)

        # Direction pill
        pill_y = ticker_y + 156
        f_pill = _get_font(24, lang)
        pill_text_w = _text_width(draw, direction_word, f_pill, 14)
        pill_w = pill_text_w + 48
        draw.rounded_rectangle([pad + 32, pill_y, pad + 32 + pill_w, pill_y + 48], radius=24,
                                fill=(dir_color[0], dir_color[1], dir_color[2]))
        draw.text((pad + 32 + 24, pill_y + 10), direction_word, font=f_pill, fill=(8, 12, 20))

        # Confidence / research score (right column)
        f_score = _get_font(110, lang)
        f_score_label = _get_font(24, lang)
        score_w = _text_width(draw, conf_str, f_score, 60)
        score_x = w - pad - 32 - max(score_w, 220)
        draw.text((score_x, ticker_y - 6), conf_str, font=f_score, fill=_CARD_ACCENT)
        score_label = _CARD_SCORE_LABEL.get(lang, _CARD_SCORE_LABEL["en"])
        label_w = _text_width(draw, score_label, f_score_label, 13)
        draw.text((w - pad - 32 - label_w, ticker_y + 118), score_label, font=f_score_label, fill=_CARD_MUTED)

        # Methodology line + disclaimer (bottom)
        f_method = _get_font(20, lang)
        method_y = h - pad - 88
        draw.line([(pad + 32, method_y - 16), (w - pad - 32, method_y - 16)], fill=(30, 41, 59), width=2)
        draw.text((pad + 32, method_y), _CARD_METHOD_LINE.get(lang, _CARD_METHOD_LINE["en"]), font=f_method, fill=_CARD_MUTED)
        f_disclaimer = _get_font(18, lang)
        draw.text((pad + 32, method_y + 32), _CARD_DISCLAIMER_SHORT.get(lang, _CARD_DISCLAIMER_SHORT["en"]),
                   font=f_disclaimer, fill=_CARD_MUTED)

        import io
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception:
        return None


def push_daily_research_card_to_telegram(cache: dict, date_str: str = ""):
    """Best-effort fan-out of today's Top Opportunity research card (image
    + localized "take" caption) to all 3 configured Telegram channels.
    Mirrors push_daily_signals_to_telegram's per-channel independence --
    one channel/lang failing (missing chat_id, render failure, network
    error) never blocks the others."""
    try:
        top = _pick_top_signal(cache)
        if not top:
            return
        date_str = date_str or cache.get("date", "")
        channels = {
            "en": os.getenv("TELEGRAM_CHANNEL_ID", ""),
            "zh": os.getenv("TELEGRAM_ZH_CHANNEL_ID", ""),
            "es": os.getenv("TELEGRAM_ES_CHANNEL_ID", ""),
        }
        for lang, chat_id in channels.items():
            if not chat_id:
                continue
            image_bytes = generate_research_card(top, lang, date_str)
            if not image_bytes:
                continue
            top_label = _tr(top.get("label") or top.get("asset_class_label") or "", _LABEL_KEYS, lang)
            top_conf = top.get("confluence_confidence_pct")
            caption = ""
            if top_conf is not None:
                caption = _INSIGHT_TEMPLATE.get(lang, _INSIGHT_TEMPLATE["en"]).format(
                    ticker=top.get("ticker", "?"), label=top_label, conf=top_conf
                )
            full_research = _FULL_RESEARCH_LABEL.get(lang, _FULL_RESEARCH_LABEL["en"])
            caption = (
                f"{caption}\n\n{full_research}: https://www.xfinlab.com/ai-analysis.html?ticker={top.get('ticker', '')}"
                f"\n{_DISCLAIMER.get(lang, _DISCLAIMER['en'])}"
            ).strip()
            send_telegram_photo(chat_id, image_bytes, caption)
    except Exception:
        pass


def push_daily_signals_to_telegram(cache: dict):
    """Best-effort fan-out of today's top signals to the 3 configured
    Telegram channels (en/zh/es). Safe to call even if some/all channel
    IDs or the bot token are unset -- each send is independently
    best-effort via send_telegram_message's own guard."""
    try:
        channels = {
            "en": os.getenv("TELEGRAM_CHANNEL_ID", ""),
            "zh": os.getenv("TELEGRAM_ZH_CHANNEL_ID", ""),
            "es": os.getenv("TELEGRAM_ES_CHANNEL_ID", ""),
        }
        for lang, chat_id in channels.items():
            if not chat_id:
                continue
            message = _build_message(cache, lang)
            send_telegram_message(chat_id, message)
    except Exception:
        pass


def send_telegram_photo(chat_id: str, image_bytes: bytes, caption: str = "") -> bool:
    """2026-08-25: daily research-card auto-post (AJ: "一個 ticker 嘅 AI
    research 截圖 + 你嘅睇法"). Uploads an in-memory PNG (no temp file --
    Railway's disk is ephemeral anyway, and this keeps the card generator
    side-effect-free) via the Bot API's sendPhoto multipart upload. Same
    best-effort posture as send_telegram_video: returns True/False, never
    raises, missing token/chat_id/bytes just short-circuits to False."""
    token = _bot_token()
    if not token or not chat_id or not image_bytes:
        return False
    try:
        res = requests.post(
            f"{TELEGRAM_API_BASE}/bot{token}/sendPhoto",
            data={"chat_id": chat_id, "caption": caption[:1024], "parse_mode": "Markdown"},
            files={"photo": ("research-card.png", image_bytes, "image/png")},
            timeout=30,
        )
        return res.status_code == 200
    except Exception:
        return False


def send_telegram_video(chat_id: str, file_path: str, caption: str = "") -> bool:
    """Growth OS Phase 7 (2026-08-04): upload one local video file to one
    Telegram chat/channel via the Bot API's sendVideo (multipart file
    upload, not a URL -- the video lives on Railway's local ephemeral
    disk, not at a public URL Telegram could fetch). Returns True on
    success, False on any failure (missing token/chat_id, file missing,
    network error, non-200 response) -- never raises, same best-effort
    posture as send_telegram_message above."""
    token = _bot_token()
    if not token or not chat_id or not file_path or not os.path.exists(file_path):
        return False
    try:
        with open(file_path, "rb") as f:
            res = requests.post(
                f"{TELEGRAM_API_BASE}/bot{token}/sendVideo",
                data={"chat_id": chat_id, "caption": caption[:1024]},
                files={"video": f},
                timeout=60,
            )
        return res.status_code == 200
    except Exception:
        return False


# Growth OS Phase 7: maps a Video Engine narration language to the
# matching Telegram channel env var. Cantonese/Mandarin variants all
# fan into the one Chinese channel (there's only one configured); ja/ko
# have no dedicated channel yet, so those are simply skipped (best-
# effort, not an error) until one is ever added.
_VIDEO_CHANNEL_ENV_BY_LANG = {
    "zh-HK": "TELEGRAM_ZH_CHANNEL_ID", "zh-CN": "TELEGRAM_ZH_CHANNEL_ID",
    "zh-TW": "TELEGRAM_ZH_CHANNEL_ID", "zh": "TELEGRAM_ZH_CHANNEL_ID",
    "en": "TELEGRAM_CHANNEL_ID",
    "es": "TELEGRAM_ES_CHANNEL_ID",
}


# 2026-08-08 fix ("TG 自動發出去到TG 群的D字都要跟法規, 而家重顯示緊 XFINLAB
# Daily Free Signals"): api/admin.py's video-post trigger used to hard-code
# caption="XFINLAB Daily AI Market Signal" for every language -- the word
# "Signal" is exactly the regulated-vocabulary term this whole site moved
# away from (task #666/#669/#671, matching _build_message()'s title dict
# above), and it never varied by lang despite this function taking one.
# Reuses the SAME compliant "XFINLAB Daily Market Intelligence" framing as
# the text push above instead of a second, drifted copy of that decision.
_VIDEO_CAPTION_BY_LANG = {
    "zh-HK": "📊 XFINLAB 每日市場情報 · 影片版\n僅供研究參考，不構成投資建議。",
    "zh-CN": "📊 XFINLAB 每日市场情报 · 视频版\n仅供研究参考，不构成投资建议。",
    "zh-TW": "📊 XFINLAB 每日市場情報 · 影片版\n僅供研究參考，不構成投資建議。",
    "zh": "📊 XFINLAB 每日市場情報 · 影片版\n僅供研究參考，不構成投資建議。",
    "en": "📊 XFINLAB Daily Market Intelligence · Video\nResearch information only. Not investment advice.",
    "es": "📊 Inteligencia de Mercado Diaria XFINLAB · Video\nSolo información de investigación. No es asesoría de inversión.",
}


def video_caption(lang: str) -> str:
    """Compliant, language-aware default caption for daily video posts --
    exported so api/admin.py's Generate Now trigger no longer needs its
    own hard-coded, English-only, non-compliant string."""
    return _VIDEO_CAPTION_BY_LANG.get(lang, _VIDEO_CAPTION_BY_LANG["en"])


def push_video_to_telegram(lang: str, file_path: str, caption: str = "") -> bool:
    """Best-effort: send the Video Engine's finished mp4 to whichever
    Telegram channel matches its narration language. Returns False (not
    an exception) if there's no channel configured for that language,
    the bot token is unset, or the send itself fails -- callers (api/
    admin.py's manual Generate Now trigger) treat this purely as an
    informational extra, never something that should fail the
    generation response it's attached to."""
    env_key = _VIDEO_CHANNEL_ENV_BY_LANG.get(lang)
    if not env_key:
        return False
    chat_id = os.getenv(env_key, "")
    if not chat_id:
        return False
    return send_telegram_video(chat_id, file_path, caption or video_caption(lang))
