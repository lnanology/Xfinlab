import os
import sys
import asyncio
sys.path.insert(0, "/Users/aj/Desktop/Xfinlab-main")

from telegram import Bot
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID")

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
    ("ES=F", "S&P 500"), ("NQ=F", "Nasdaq"), ("YM=F", "Dow Jones"),
    ("RTY=F", "Russell 2000"), ("GC=F", "Gold"), ("SI=F", "Silver"),
    ("CL=F", "Crude Oil"), ("NG=F", "Natural Gas"), ("HG=F", "Copper"),
    ("ZB=F", "30Y Bond"), ("6E=F", "EUR/USD"), ("6J=F", "JPY/USD"),
    ("6B=F", "GBP/USD"), ("PL=F", "Platinum"), ("PA=F", "Palladium"),
    ("ZC=F", "Corn"), ("ZW=F", "Wheat"), ("ZS=F", "Soybean"),
    ("VX=F", "VIX"), ("ZN=F", "10Y Note"),
]


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
        import requests, time
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
            "market_cap": c["market_cap"]
        } for c in data]
    except Exception as e:
        print(f"Crypto error: {e}")
        return []


def get_top_futures(n=20):
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


async def push_daily_analysis():
    bot = Bot(token=TOKEN)

    try:
        from services.market_data_service import MarketDataService
        from engines.news_engine import NewsEngine
        from services.news_service import NewsService

        market_svc = MarketDataService()
        news_svc = NewsService()

        # Core Watchlist
        msg = "📊 *XFINLAB Daily Intelligence*\n"
        msg += "━━━━━━━━━━━━━━━━━━━━\n\n"
        msg += "🔵 *Core Watchlist*\n\n"

        for symbol in CORE_SYMBOLS:
            try:
                market = market_svc.get_stock_data(symbol)
                news = news_svc.get_company_news(symbol)
                news_result = NewsEngine.analyze([
                    {"title": a["title"], "summary": a["title"]}
                    for a in news[:5]
                ])
                price = market.get("price", "N/A")
                sentiment = news_result["sentiment"]
                emoji = "🟢" if sentiment == "Positive" else "🔴" if sentiment == "Negative" else "🟡"
                msg += f"{emoji} *{symbol}* — ${price} | {sentiment}\n"
            except:
                msg += f"⚪ *{symbol}* — Unavailable\n"

        # Top 20 Stocks
        msg += "\n━━━━━━━━━━━━━━━━━━━━\n"
        msg += "🔥 *Top 20 Most Active Stocks*\n\n"
        volume_stocks = get_top_volume_stocks(20)
        if volume_stocks:
            for stock in volume_stocks:
                ratio = stock["volume_ratio"]
                spike = "🚀" if ratio > 3 else "⚡" if ratio > 2 else "📈"
                msg += f"{spike} *{stock['symbol']}* — ${stock['price']} | Vol {ratio}x\n"
        else:
            msg += "Data unavailable\n"

        # Top 20 Crypto
        msg += "\n━━━━━━━━━━━━━━━━━━━━\n"
        msg += "₿ *Top 20 Crypto by Volume*\n\n"
        crypto_list = get_top_crypto(20)
        if crypto_list:
            for coin in crypto_list:
                vol = coin["volume_24h"]
                vol_str = f"${vol/1e9:.1f}B" if vol > 1e9 else f"${vol/1e6:.0f}M"
                msg += f"💎 *{coin['symbol']}* — ${coin['price']:,.2f} | Vol {vol_str}\n"
        else:
            msg += "Data unavailable\n"

        # Top 20 Futures
        msg += "\n━━━━━━━━━━━━━━━━━━━━\n"
        msg += "📈 *Top 20 Futures*\n\n"
        futures_list = get_top_futures(20)
        if futures_list:
            for f in futures_list:
                chg = f["change_pct"]
                emoji = "🟢" if chg > 0 else "🔴" if chg < 0 else "⚪"
                sign = "+" if chg > 0 else ""
                msg += f"{emoji} *{f['name']}* ({f['symbol']}) — ${f['price']} | {sign}{chg}%\n"
        else:
            msg += "Data unavailable\n"

        msg += "\n━━━━━━━━━━━━━━━━━━━━\n"
        msg += "🔗 [Full Analysis](https://finlab-ai.vercel.app)"

        await bot.send_message(
            chat_id=CHANNEL_ID,
            text=msg,
            parse_mode='Markdown'
        )
        print("English channel pushed!")

    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    asyncio.run(push_daily_analysis())
