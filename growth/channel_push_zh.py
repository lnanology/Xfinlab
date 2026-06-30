import os
import sys
import asyncio
sys.path.insert(0, "/Users/aj/Desktop/Xfinlab-main")

from telegram import Bot
from dotenv import load_dotenv
from ai.ai_router import get_ai_response

load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ZH_CHANNEL_ID = os.getenv("TELEGRAM_ZH_CHANNEL_ID")

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

TOP_FUTURES = [
    ("ES=F", "標普500"), ("NQ=F", "納斯達克"), ("YM=F", "道瓊斯"),
    ("GC=F", "黃金"), ("SI=F", "白銀"), ("CL=F", "原油"),
    ("NG=F", "天然氣"), ("HG=F", "銅"), ("ZB=F", "30年國債"),
    ("6E=F", "歐元"), ("6J=F", "日圓"), ("6B=F", "英鎊"),
]


def translate_sentiment(sentiment: str) -> str:
    mapping = {"Positive": "正面", "Negative": "負面", "Neutral": "中性"}
    return mapping.get(sentiment, sentiment)


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
            except:
                pass
        results.sort(key=lambda x: x["volume_ratio"], reverse=True)
        return results[:n]
    except:
        return []


def get_top_crypto(n=20):
    try:
        from services.crypto_service import CryptoService
        svc = CryptoService()
        results = []
        import time
        for coin_id in TOP_CRYPTO:
            try:
                data = svc.get_crypto_data(coin_id)
                if data:
                    results.append(data)
            except:
                pass
            time.sleep(0.5)
        results.sort(key=lambda x: x["volume_24h"], reverse=True)
        return results[:n]
    except:
        return []


def get_top_futures(n=12):
    try:
        import yfinance as yf
        results = []
        for ticker, name in TOP_FUTURES[:n]:
            try:
                t = yf.Ticker(ticker)
                info = t.info
                price = info.get("regularMarketPrice") or info.get("previousClose", 0)
                change = info.get("regularMarketChangePercent", 0)
                results.append({
                    "symbol": ticker.replace("=F", ""),
                    "name": name,
                    "price": round(price, 2) if price else 0,
                    "change_pct": round(change, 2) if change else 0
                })
            except:
                pass
        results.sort(key=lambda x: abs(x["change_pct"]), reverse=True)
        return results
    except:
        return []


async def push_zh_analysis():
    bot = Bot(token=TOKEN)

    try:
        from services.market_data_service import MarketDataService
        from engines.news_engine import NewsEngine
        from services.news_service import NewsService

        market_svc = MarketDataService()
        news_svc = NewsService()

        # ── 核心觀察股 ──────────────────────────────
        msg = "📊 *XFINLAB 每日智能分析*\n"
        msg += "━━━━━━━━━━━━━━━━━━━━\n\n"
        msg += "🔵 *核心觀察股*\n\n"

        for symbol in CORE_SYMBOLS:
            try:
                market = market_svc.get_stock_data(symbol)
                news = news_svc.get_company_news(symbol)
                news_result = NewsEngine.analyze([
                    {"title": a["title"], "summary": a["title"]}
                    for a in news[:5]
                ])
                price = market.get("price", "N/A")
                sentiment = translate_sentiment(news_result["sentiment"])
                emoji = "🟢" if news_result["sentiment"] == "Positive" else "🔴" if news_result["sentiment"] == "Negative" else "🟡"
                msg += f"{emoji} *{symbol}* — ${price} | {sentiment}\n"
            except:
                msg += f"⚪ *{symbol}* — 數據不可用\n"

        # ── 最活躍股票 ──────────────────────────────
        msg += "\n━━━━━━━━━━━━━━━━━━━━\n"
        msg += "🔥 *成交量最活躍 Top 20*\n\n"

        volume_stocks = get_top_volume_stocks(20)
        if volume_stocks:
            for stock in volume_stocks:
                ratio = stock["volume_ratio"]
                spike = "🚀" if ratio > 3 else "⚡" if ratio > 2 else "📈"
                msg += f"{spike} *{stock['symbol']}* — ${stock['price']} | 成交量 {ratio}x\n"
        else:
            msg += "數據不可用\n"

        # ── 加密貨幣 ────────────────────────────────
        msg += "\n━━━━━━━━━━━━━━━━━━━━\n"
        msg += "₿ *加密貨幣 Top 20*\n\n"

        crypto_list = get_top_crypto(20)
        if crypto_list:
            for coin in crypto_list:
                vol = coin["volume_24h"]
                vol_str = f"${vol/1e9:.1f}B" if vol > 1e9 else f"${vol/1e6:.0f}M"
                msg += f"💎 *{coin['symbol']}* — ${coin['price']:,.2f} | 成交額 {vol_str}\n"
        else:
            msg += "數據不可用\n"

        # ── 期貨市場 ────────────────────────────────
        msg += "\n━━━━━━━━━━━━━━━━━━━━\n"
        msg += "📈 *期貨市場*\n\n"

        futures_list = get_top_futures(12)
        if futures_list:
            for f in futures_list:
                chg = f["change_pct"]
                emoji = "🟢" if chg > 0 else "🔴" if chg < 0 else "⚪"
                sign = "+" if chg > 0 else ""
                msg += f"{emoji} *{f['name']}* ({f['symbol']}) — ${f['price']} | {sign}{chg}%\n"
        else:
            msg += "數據不可用\n"

        msg += "\n━━━━━━━━━━━━━━━━━━━━\n"
        msg += "🔗 [完整分析](https://finlab-ai.vercel.app)"

        await bot.send_message(
            chat_id=ZH_CHANNEL_ID,
            text=msg,
            parse_mode='Markdown'
        )
        print("中文分析推送成功！")

    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    asyncio.run(push_zh_analysis())
