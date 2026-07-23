# 2026-07-23 note (platform audit finding): this file is superseded and NOT
# the live Telegram bot anymore. It's a polling-mode bot (Application.
# run_polling(), a long-running blocking loop) that needs its own process --
# Railway's Procfile only starts `uvicorn backend.main:app` (see Procfile /
# railway.json), so this file was never actually reachable in production;
# nobody who ever messaged the bot's /analyze, /screener, or /portfolio
# commands got a real reply. Also hardcodes a local Mac path (sys.path
# below) and hits API_BASE="http://127.0.0.1:8002", a port this app doesn't
# even run on.
#
# The real, live bot is now api/telegram_webhook.py -- same commands,
# webhook-based (Telegram POSTs updates to our existing FastAPI app, no
# second process needed), reusing the already-configured
# TELEGRAM_BOT_TOKEN. Kept here unmodified as the original prototype rather
# than deleted, per this repo's convention of not removing files without
# asking.
import os
import sys
sys.path.insert(0, "/Users/aj/Desktop/Xfinlab-main")

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
API_BASE = "http://127.0.0.1:8002/api"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🚀 Welcome to XFINLAB Intelligence!\n\n"
        "Commands:\n"
        "/analyze AAPL - Full stock analysis\n"
        "/screener - Top stock picks\n"
        "/portfolio - Portfolio allocation\n"
        "/help - Show commands"
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📊 XFINLAB Commands:\n\n"
        "/analyze [TICKER] - AI stock analysis\n"
        "/screener - Top opportunities\n"
        "/portfolio - Portfolio allocation\n\n"
        "Example: /analyze NVDA"
    )


async def analyze(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Please provide a ticker. Example: /analyze AAPL")
        return

    ticker = context.args[0].upper()
    await update.message.reply_text(f"⏳ Analyzing {ticker}...")

    try:
        import requests
        res = requests.get(f"{API_BASE}/full-analysis/{ticker}", timeout=30)
        data = res.json()

        msg = (
            f"📊 *{ticker} Analysis*\n\n"
            f"💰 Price: ${data.get('price', 'N/A')}\n"
            f"📈 Market Score: {data.get('market_score', 0):.1f}/100\n"
            f"📰 News Score: {data.get('news_score', 0):.1f}/100\n"
            f"⚠️ Risk: {data.get('risk', {}).get('risk_level', 'N/A')}\n"
            f"🎯 Final Score: {data.get('final_score', 0):.1f}/100\n"
            f"✅ Rating: *{data.get('rating', 'N/A')}*"
        )
        await update.message.reply_text(msg, parse_mode='Markdown')

    except Exception as e:
        await update.message.reply_text(f"❌ Error analyzing {ticker}: {str(e)}")


async def screener(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Running screener...")
    try:
        import requests
        res = requests.get(f"{API_BASE}/screener", timeout=15)
        data = res.json()

        results = data.get("results", [])
        if not results:
            await update.message.reply_text("No stocks passed the screener filter.")
            return

        msg = "📊 *Top Stock Picks*\n\n"
        for i, stock in enumerate(results[:5], 1):
            msg += f"{i}. *{stock['ticker']}* — Score: {stock['final_score']}\n"

        await update.message.reply_text(msg, parse_mode='Markdown')

    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")


async def portfolio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Loading portfolio...")
    try:
        import requests
        res = requests.get(f"{API_BASE}/portfolio", timeout=15)
        data = res.json()

        allocs = data.get("portfolio", [])
        msg = "💼 *Portfolio Allocation*\n\n"
        for stock in allocs:
            msg += f"• *{stock['ticker']}*: {stock['allocation']}%\n"

        await update.message.reply_text(msg, parse_mode='Markdown')

    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")


def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("analyze", analyze))
    app.add_handler(CommandHandler("screener", screener))
    app.add_handler(CommandHandler("portfolio", portfolio))

    print("XFINLAB Telegram Bot starting...")
    app.run_polling()


if __name__ == "__main__":
    main()
