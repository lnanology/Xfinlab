"""
XFINLAB Telegram Channel Push — Unified Multi-Language Version

Replaces channel_push.py / channel_push_zh.py / channel_push_es.py.
Pushes the daily market briefing to the EN / ZH / ES channels in one run.

Designed to run as a Railway Cron Job:
  Start command: python growth/channel_push_all.py
  Cron schedule: 30 1 * * *   (= 09:30 Asia/Hong_Kong, Railway cron is UTC)

Env vars required:
  TELEGRAM_BOT_TOKEN
  TELEGRAM_CHANNEL_ID       (English channel)
  TELEGRAM_ZH_CHANNEL_ID    (Chinese channel)
  TELEGRAM_ES_CHANNEL_ID    (Spanish channel)
"""

import os
import sys
import asyncio
import time

# Portable path setup — works on any machine/server, not just one Mac.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from telegram import Bot
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# lang -> channel id env var
CHANNELS = {
    "en": os.getenv("TELEGRAM_CHANNEL_ID"),
    "zh": os.getenv("TELEGRAM_ZH_CHANNEL_ID"),
    "es": os.getenv("TELEGRAM_ES_CHANNEL_ID"),
}

CORE_SYMBOLS = ["AAPL", "NVDA", "TSLA", "MSFT", "META"]

TOP_ACTIVE = [
    "AAPL", "NVDA", "TSLA", "MSFT", "META",
    "AMZN", "GOOGL", "AMD", "PLTR", "NFLX",
    "BABA", "COIN", "MSTR", "SOFI", "RIVN",
    "NIO", "UBER", "SHOP", "SQ", "HOOD"
]

TOP_CRYPTO = [
    "bitcoin", "ethereum", "solana", "binancecoin", "ripple",
    "cardano", "dogecoin", "avalanche-2", "polkadot", "chainlink",
    "litecoin", "uniswap", "stellar", "monero", "cosmos",
    "algorand", "vechain", "filecoin", "tron", "eos"
]

# ticker -> {lang: display name}
TOP_FUTURES = [
    ("ES=F", {"en": "S&P 500", "zh": "標普500", "es": "S&P 500"}),
    ("NQ=F", {"en": "Nasdaq", "zh": "納斯達克", "es": "Nasdaq"}),
    ("YM=F", {"en": "Dow Jones", "zh": "道瓊斯", "es": "Dow Jones"}),
    ("RTY=F", {"en": "Russell 2000", "zh": "羅素2000", "es": "Russell 2000"}),
    ("GC=F", {"en": "Gold", "zh": "黃金", "es": "Oro"}),
    ("SI=F", {"en": "Silver", "zh": "白銀", "es": "Plata"}),
    ("CL=F", {"en": "Crude Oil", "zh": "原油", "es": "Petróleo"}),
    ("NG=F", {"en": "Natural Gas", "zh": "天然氣", "es": "Gas Natural"}),
    ("HG=F", {"en": "Copper", "zh": "銅", "es": "Cobre"}),
    ("ZB=F", {"en": "30Y Bond", "zh": "30年國債", "es": "Bono 30A"}),
    ("6E=F", {"en": "EUR/USD", "zh": "歐元", "es": "EUR/USD"}),
    ("6J=F", {"en": "JPY/USD", "zh": "日圓", "es": "JPY/USD"}),
    ("6B=F", {"en": "GBP/USD", "zh": "英鎊", "es": "GBP/USD"}),
    ("PL=F", {"en": "Platinum", "zh": "鉑金", "es": "Platino"}),
    ("PA=F", {"en": "Palladium", "zh": "鈀金", "es": "Paladio"}),
    ("ZC=F", {"en": "Corn", "zh": "玉米", "es": "Maíz"}),
    ("ZW=F", {"en": "Wheat", "zh": "小麥", "es": "Trigo"}),
    ("ZS=F", {"en": "Soybean", "zh": "大豆", "es": "Soja"}),
    ("VX=F", {"en": "VIX", "zh": "VIX恐慌指數", "es": "VIX"}),
    ("ZN=F", {"en": "10Y Note", "zh": "10年國債", "es": "Bono 10A"}),
]

SENTIMENT = {
    "en": {"Positive": "Positive", "Negative": "Negative", "Neutral": "Neutral"},
    "zh": {"Positive": "正面", "Negative": "負面", "Neutral": "中性"},
    "es": {"Positive": "Positivo", "Negative": "Negativo", "Neutral": "Neutral"},
}

TEXT = {
    "en": {
        "title": "🚀 *XFINLAB Daily Intelligence*",
        "core": "🔵 *Core Watchlist*",
        "top_stocks": "🔥 *Top 20 Most Active Stocks*",
        "top_crypto": "₿ *Top 20 Crypto by Volume*",
        "top_futures": "📈 *Top 20 Futures*",
        "unavailable": "Data unavailable",
        "symbol_unavailable": "Unavailable",
        "vol_label": "vol",
        "footer": "🔗 [Full AI Analysis](https://xfinlab.com)\n📊 [Dashboard](https://xfinlab.com/dashboard.html)",
        "sent_log": "English channel pushed!",
    },
    "zh": {
        "title": "📊 *XFINLAB 每日智能分析*",
        "core": "🔵 *核心觀察股*",
        "top_stocks": "🔥 *成交量最活躍 Top 20*",
        "top_crypto": "₿ *加密貨幣 Top 20*",
        "top_futures": "📈 *期貨市場 Top 20*",
        "unavailable": "數據不可用",
        "symbol_unavailable": "數據不可用",
        "vol_label": "成交量",
        "footer": "🔗 [完整分析](https://xfinlab.com)\n📊 [儀表板](https://xfinlab.com/dashboard.html)",
        "sent_log": "中文分析推送成功！",
    },
    "es": {
        "title": "🚀 *XFINLAB Análisis Diario*",
        "core": "🔵 *Acciones Principales*",
        "top_stocks": "🔥 *Top 20 Más Activas*",
        "top_crypto": "₿ *Criptomonedas Top 20*",
        "top_futures": "📈 *Mercado de Futuros Top 20*",
        "unavailable": "Datos no disponibles",
        "symbol_unavailable": "No disponible",
        "vol_label": "Vol",
        "footer": "🔗 [Análisis Completo](https://xfinlab.com)\n📊 [Panel](https://xfinlab.com/dashboard.html)",
        "sent_log": "¡Análisis en español enviado!",
    },
}


def get_top_volume_stocks(n=20):
    try:
        from services.market_data_service import MarketDataService
        svc = MarketDataService()
        results = []
        for symbol in TOP_ACTIVE:
            try:
                data = svc.get_stock_data(symbol)
                volume = data.get("volume", 0)
                avg_volume = data.get("avg_volume", 1)
                volume_ratio = round(volume / avg_volume, 2) if avg_volume > 0 else 0
                results.append({
                    "symbol": symbol,
                    "price": data.get("price", 0),
                    "volume_ratio": volume_ratio
                })
            except Exception:
                pass
        results.sort(key=lambda x: x["volume_ratio"], reverse=True)
        return results[:n]
    except Exception:
        return []


def get_top_crypto(n=20):
    try:
        import requests
        ids = ",".join(TOP_CRYPTO[:n])
        url = f"https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&ids={ids}&order=volume_desc&per_page={n}&page=1"
        res = requests.get(url, timeout=15)
        if res.status_code == 429:
            time.sleep(10)
            res = requests.get(url, timeout=15)
        data = res.json()
        return [{
            "symbol": c["symbol"].upper(),
            "price": c["current_price"],
            "volume_24h": c["total_volume"],
            "change_24h": c.get("price_change_percentage_24h", 0)
        } for c in data]
    except Exception as e:
        print(f"Crypto error: {e}")
        return []


def get_top_futures(lang, n=20):
    try:
        import yfinance as yf
        results = []
        for ticker, names in TOP_FUTURES[:n]:
            try:
                t = yf.Ticker(ticker)
                info = t.info
                price = info.get("regularMarketPrice") or info.get("previousClose", 0)
                change = info.get("regularMarketChangePercent", 0)
                results.append({
                    "symbol": ticker.replace("=F", ""),
                    "name": names.get(lang, names["en"]),
                    "price": round(price, 2) if price else 0,
                    "change_pct": round(change, 2) if change else 0
                })
            except Exception:
                pass
        results.sort(key=lambda x: abs(x["change_pct"]), reverse=True)
        return results
    except Exception:
        return []


def build_message(lang, market_svc, news_svc, volume_stocks, crypto_list, futures_list):
    from engines.news_engine import NewsEngine

    t = TEXT[lang]
    date_str = datetime.now().strftime("%Y/%m/%d")
    weekday = datetime.now().strftime("%A")

    msg = f"{t['title']}\n📅 {date_str} · {weekday}\n"
    msg += "━━━━━━━━━━━━━━━━━━━━\n\n"

    msg += f"{t['core']}\n"
    for symbol in CORE_SYMBOLS:
        try:
            market = market_svc.get_stock_data(symbol)
            news = news_svc.get_company_news(symbol)
            news_result = NewsEngine.analyze([
                {"title": a["title"], "summary": a["title"]} for a in news[:5]
            ])
            price = market.get("price", "N/A")
            raw_sentiment = news_result["sentiment"]
            sentiment = SENTIMENT[lang].get(raw_sentiment, raw_sentiment)
            emoji = "🟢" if raw_sentiment == "Positive" else "🔴" if raw_sentiment == "Negative" else "🟡"
            msg += f"{emoji} `{symbol}` ${price} · {sentiment}\n"
        except Exception:
            msg += f"⚪ `{symbol}` · {t['symbol_unavailable']}\n"

    msg += f"\n{t['top_stocks']}\n"
    if volume_stocks:
        for stock in volume_stocks:
            ratio = stock["volume_ratio"]
            spike = "🚀" if ratio > 3 else "⚡" if ratio > 2 else "📈"
            msg += f"{spike} `{stock['symbol']}` ${stock['price']} · {ratio}x {t['vol_label']}\n"
    else:
        msg += f"{t['unavailable']}\n"

    msg += f"\n{t['top_crypto']}\n"
    if crypto_list:
        for coin in crypto_list:
            vol = coin["volume_24h"]
            vol_str = f"${vol/1e9:.1f}B" if vol > 1e9 else f"${vol/1e6:.0f}M"
            chg = coin.get("change_24h", 0)
            chg_emoji = "🟢" if chg > 0 else "🔴"
            sign = "+" if chg > 0 else ""
            msg += f"{chg_emoji} `{coin['symbol']}` ${coin['price']:,.2f} · {sign}{chg:.1f}% · {t['vol_label']} {vol_str}\n"
    else:
        msg += f"{t['unavailable']}\n"

    msg += f"\n{t['top_futures']}\n"
    if futures_list:
        for f in futures_list:
            chg = f["change_pct"]
            emoji = "🟢" if chg > 0 else "🔴" if chg < 0 else "⚪"
            sign = "+" if chg > 0 else ""
            msg += f"{emoji} `{f['symbol']}` ({f['name']}) ${f['price']} · {sign}{chg}%\n"
    else:
        msg += f"{t['unavailable']}\n"

    msg += "\n━━━━━━━━━━━━━━━━━━━━\n"
    msg += t["footer"]
    return msg


async def push_all():
    if not TOKEN:
        print("Missing TELEGRAM_BOT_TOKEN — aborting.")
        return

    bot = Bot(token=TOKEN)

    from services.market_data_service import MarketDataService
    from services.news_service import NewsService

    market_svc = MarketDataService()
    news_svc = NewsService()

    volume_stocks = get_top_volume_stocks(20)
    crypto_list = get_top_crypto(20)

    for lang, chat_id in CHANNELS.items():
        if not chat_id:
            print(f"[{lang}] Skipped — no channel ID configured (check env var).")
            continue

        futures_list = get_top_futures(lang, 20)

        try:
            msg = build_message(lang, market_svc, news_svc, volume_stocks, crypto_list, futures_list)
            await bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")
            print(TEXT[lang]["sent_log"])
        except Exception as e:
            print(f"[{lang}] Error sending message: {e}")

        await asyncio.sleep(3)


if __name__ == "__main__":
    asyncio.run(push_all())
