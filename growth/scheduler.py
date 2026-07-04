import os
import sys
sys.path.insert(0, "/Users/aj/Desktop/Xfinlab-main")

from apscheduler.schedulers.blocking import BlockingScheduler
from datetime import datetime

scheduler = BlockingScheduler(timezone="Asia/Hong_Kong")


def daily_analysis():
    """每日早上9點自動分析熱門股"""
    from services.market_data_service import MarketDataService
    from engines.news_engine import NewsEngine
    from services.news_service import NewsService

    symbols = ["AAPL", "NVDA", "TSLA", "MSFT", "META"]
    market_svc = MarketDataService()
    news_svc = NewsService()

    print(f"[{datetime.now()}] Running daily analysis...")

    results = []
    for symbol in symbols:
        try:
            market = market_svc.get_stock_data(symbol)
            news = news_svc.get_company_news(symbol)
            news_result = NewsEngine.analyze([{"title": a["title"], "summary": a["title"]} for a in news[:5]])

            results.append({
                "symbol": symbol,
                "price": market.get("price"),
                "news_sentiment": news_result["sentiment"],
                "news_score": news_result["score"]
            })
            print(f"  {symbol}: ${market.get('price')} | {news_result['sentiment']}")
        except Exception as e:
            print(f"  {symbol}: Error - {e}")

    print(f"[{datetime.now()}] Daily analysis complete - {len(results)} stocks analyzed")
    return results


def weekly_report():
    """每週一生成週報"""
    print(f"[{datetime.now()}] Generating weekly report...")
    # 之後可以加 Email 發送
    print(f"[{datetime.now()}] Weekly report complete")


# 每日 9:00 AM 香港時間
scheduler.add_job(daily_analysis, 'cron', hour=9, minute=0)

# 每週一 8:00 AM
scheduler.add_job(weekly_report, 'cron', day_of_week='mon', hour=8, minute=0)


async def push_zh_channel():
    import subprocess
    subprocess.run([
        "/Library/Developer/CommandLineTools/usr/bin/python3.9",
        "/Users/aj/Desktop/Xfinlab-main/growth/channel_push_zh.py"
    ])

scheduler.add_job(push_zh_channel, "cron", hour=9, minute=35)

async def push_es_channel():
    import subprocess
    subprocess.run([
        "/Library/Developer/CommandLineTools/usr/bin/python3.9",
        "/Users/aj/Desktop/Xfinlab-main/growth/channel_push_es.py"
    ])

scheduler.add_job(push_es_channel, "cron", hour=9, minute=40)

async def check_anomalies():
    import subprocess
    subprocess.run([
        "/Library/Developer/CommandLineTools/usr/bin/python3.9",
        "/Users/aj/Desktop/Xfinlab-main/growth/anomaly_alerts.py"
    ])

scheduler.add_job(check_anomalies, "interval", minutes=30)

async def generate_fb_content():
    import subprocess
    subprocess.run([
        "python3",
        "/Users/aj/Desktop/Xfinlab-main/growth/media/facebook_generator.py"
    ])

scheduler.add_job(generate_fb_content, "cron", hour=8, minute=30)

async def push_channel():
    import subprocess
    subprocess.run([
        "/Library/Developer/CommandLineTools/usr/bin/python3.9",
        "/Users/aj/Desktop/Xfinlab-main/growth/channel_push.py"
    ])

scheduler.add_job(push_channel, 'cron', hour=9, minute=30)

if __name__ == "__main__":
    print("XFINLAB Scheduler starting...")
    print("Jobs scheduled:")
    print("  - Daily Analysis: 9:00 AM HKT")
    print("  - Weekly Report:  8:00 AM Monday HKT")

    # 啟動時先跑一次
    print("\nRunning initial analysis...")
    daily_analysis()

    print("\nScheduler running... Press Ctrl+C to stop")
    scheduler.start()
