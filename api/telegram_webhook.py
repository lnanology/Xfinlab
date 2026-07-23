"""
Telegram interactive bot -- webhook version.

2026-07-23 platform audit finding: growth/telegram_bot.py (python-telegram-
bot, Application.run_polling()) was never actually reachable in production.
It's a long-running polling process; Railway's Procfile only starts
`uvicorn backend.main:app` (see railway.json / Procfile) -- there is no
second worker process to run a polling loop, so /start, /analyze, /screener,
/portfolio never got a real response from anyone who messaged the bot.

This is the real, live replacement: Telegram supports webhooks (Telegram
calls a URL on our server for every incoming message) instead of polling,
which fits naturally into the existing single-process FastAPI app -- no
second process needed. Reuses TELEGRAM_BOT_TOKEN (already configured, see
services/telegram_push_service.py) and its plain-HTTPS send_telegram_message
helper instead of adding the python-telegram-bot dependency.

One-time activation step this file cannot do for you: Telegram needs to be
told where to send updates. After this deploys, call (once):
  https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/setWebhook?url=https://<your-domain>/api/telegram/webhook
Optionally set TELEGRAM_WEBHOOK_SECRET too and pass &secret_token=<value> in
that same setWebhook call -- if set, this endpoint checks Telegram's
X-Telegram-Bot-Api-Secret-Token header matches before doing any work.
growth/telegram_bot.py is left in place (not deleted) as the original
polling-mode prototype, but is no longer the live path.
"""
import os
import logging

from fastapi import APIRouter, Request

from services.telegram_push_service import send_telegram_message

logger = logging.getLogger(__name__)
router = APIRouter()


def _reply(chat_id, text: str):
    if chat_id is not None:
        send_telegram_message(str(chat_id), text, parse_mode="Markdown")


async def _handle_analyze(chat_id, args: str):
    ticker = (args or "").strip().split()[0].upper() if (args or "").strip() else None
    if not ticker:
        _reply(chat_id, "請提供代號，例如：`/analyze AAPL`")
        return
    _reply(chat_id, f"⏳ 分析緊 {ticker}...")
    try:
        from api.full_analysis_v3 import full_analysis
        data = await full_analysis(ticker, token=None)
        msg = (
            f"📊 *{ticker} 分析*\n\n"
            f"💰 現價：${data.price}\n"
            f"📈 市場評分：{data.market_score:.1f}/100\n"
            f"📰 新聞評分：{data.news_score:.1f}/100\n"
            f"⚠️ 風險：{data.risk.get('risk_level', 'N/A')}\n"
            f"🎯 綜合評分：{data.final_score:.1f}/100\n"
            f"✅ 評級：*{data.rating}*\n\n"
            f"⚠️ 僅供研究參考，不構成投資建議。"
        )
        _reply(chat_id, msg)
    except Exception as e:
        logger.warning(f"[telegram_webhook] analyze({ticker}) failed: {e}")
        _reply(chat_id, f"❌ {ticker} 分析失敗，請稍後再試。")


def _handle_screener(chat_id):
    try:
        from api.screener import screener
        result = screener(token=None)
        rows = result if isinstance(result, list) else result.get("results", [])
        if not rows:
            _reply(chat_id, "目前冇股票通過篩選條件。")
            return
        lines = ["📊 *篩選結果 Top 5*\n"]
        for i, s in enumerate(rows[:5], 1):
            lines.append(f"{i}. *{s.get('ticker', '?')}* — 評分：{s.get('final_score', '-')}")
        lines.append("\n⚠️ 僅供研究參考，不構成投資建議。")
        _reply(chat_id, "\n".join(lines))
    except Exception as e:
        logger.warning(f"[telegram_webhook] screener failed: {e}")
        _reply(chat_id, "❌ 篩選器暫時不可用，請稍後再試。")


def _handle_portfolio(chat_id):
    try:
        from api.portfolio import portfolio
        result = portfolio(token=None)
        allocs = result if isinstance(result, list) else result.get("portfolio", [])
        if not allocs:
            _reply(chat_id, "目前冇可用嘅配置建議。")
            return
        lines = ["💼 *組合配置建議*\n"]
        for a in allocs:
            lines.append(f"• *{a.get('ticker', '?')}*：{a.get('allocation', '-')}%")
        lines.append("\n⚠️ 僅供研究參考，不構成投資建議。")
        _reply(chat_id, "\n".join(lines))
    except Exception as e:
        logger.warning(f"[telegram_webhook] portfolio failed: {e}")
        _reply(chat_id, "❌ 組合配置暫時不可用，請稍後再試。")


_HELP_TEXT = (
    "🚀 *XFINLAB Intelligence*\n\n"
    "指令：\n"
    "/analyze AAPL - 完整股票分析\n"
    "/screener - 篩選結果 Top 5\n"
    "/portfolio - 組合配置建議\n"
    "/help - 顯示指令\n\n"
    "例如：`/analyze NVDA`"
)


@router.post("/telegram/webhook")
async def telegram_webhook(request: Request):
    # Optional shared-secret check (mirrors the admin-panel IP-allowlist
    # pattern: best-effort, only enforced if the operator configured it).
    expected_secret = os.getenv("TELEGRAM_WEBHOOK_SECRET")
    if expected_secret:
        got = request.headers.get("x-telegram-bot-api-secret-token")
        if got != expected_secret:
            return {"ok": True}  # silently drop, never reveal the check exists

    try:
        update = await request.json()
    except Exception:
        return {"ok": True}

    message = update.get("message") or update.get("edited_message") or {}
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    text = (message.get("text") or "").strip()

    if not chat_id or not text:
        return {"ok": True}

    parts = text.split(maxsplit=1)
    command = parts[0].split("@")[0].lower()  # strip /cmd@BotName form
    args = parts[1] if len(parts) > 1 else ""

    try:
        if command == "/start":
            _reply(chat_id, _HELP_TEXT)
        elif command == "/help":
            _reply(chat_id, _HELP_TEXT)
        elif command == "/analyze":
            await _handle_analyze(chat_id, args)
        elif command == "/screener":
            _handle_screener(chat_id)
        elif command == "/portfolio":
            _handle_portfolio(chat_id)
        # Unknown text/commands are silently ignored rather than replied to
        # -- avoids the bot spamming a reply to every random message in a
        # group chat it might get added to.
    except Exception as e:
        logger.warning(f"[telegram_webhook] unhandled error: {e}")

    # Always 200 -- Telegram retries (and eventually disables) webhooks
    # that don't return 200 quickly.
    return {"ok": True}
