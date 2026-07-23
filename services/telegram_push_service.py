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

TELEGRAM_API_BASE = "https://api.telegram.org"


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


def _fmt_signal_line(sig: dict) -> str:
    ticker = sig.get("ticker", "?")
    label = sig.get("label") or sig.get("asset_class_label") or ""
    direction = sig.get("confluence_direction", "")
    conf = sig.get("confluence_confidence_pct")
    conf_str = f"{conf}%" if conf is not None else "N/A"
    dir_emoji = "🟢" if str(direction).lower() in ("bull", "bullish", "up", "long") else (
        "🔴" if str(direction).lower() in ("bear", "bearish", "down", "short") else "⚪"
    )
    return f"{dir_emoji} *{ticker}* {label} — {direction} ({conf_str})"


def _build_message(cache: dict, lang: str) -> str:
    signals = (cache.get("signals") or [])[:5]
    date_str = cache.get("date", "")
    lines = [_fmt_signal_line(s) for s in signals]
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
