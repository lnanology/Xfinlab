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
    return f"{dir_emoji} *{ticker}* {label} — {direction} ({conf_str})"


def _build_message(cache: dict, lang: str) -> str:
    signals = (cache.get("signals") or [])[:5]
    date_str = cache.get("date", "")
    lines = [_fmt_signal_line(s, lang) for s in signals]
    body = "\n".join(lines) if lines else {
        "en": "No strong signals today.",
        "zh": "今日暫無強烈訊號。",
        "es": "Hoy no hay señales fuertes.",
    }.get(lang, "No strong signals today.")

    if lang == "zh":
        header = f"🎯 *XFINLAB 每日免費訊號* — {date_str}\n\n"
        footer = "\n\n免費完整分析: https://www.xfinlab.com/free-signals.html\n⚠️ 僅供參考，不構成投資建議。"
    elif lang == "es":
        header = f"🎯 *Señales Diarias Gratuitas de XFINLAB* — {date_str}\n\n"
        footer = "\n\nAnálisis completo gratis: https://www.xfinlab.com/free-signals.html\n⚠️ Solo con fines informativos, no es asesoría de inversión."
    else:
        header = f"🎯 *XFINLAB Daily Free Signals* — {date_str}\n\n"
        footer = "\n\nFull free analysis: https://www.xfinlab.com/free-signals.html\n⚠️ For informational purposes only, not investment advice."

    return header + body + footer


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
