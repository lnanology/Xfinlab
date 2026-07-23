# 2026-07-23 note (platform audit finding): this ENTIRE file is dead code
# in production. It's a standalone script meant to be run via
# `python growth/scheduler.py` (see the BlockingScheduler.start() call at
# the bottom) -- Railway's Procfile only ever runs `uvicorn
# backend.main:app` (see Procfile / railway.json), so nothing below has
# ever actually fired on the live site. It also hardcodes local Mac paths
# (sys.path below, and every subprocess.run([...]) call further down
# points at "/Library/Developer/CommandLineTools/usr/bin/python3.9" and
# "/Users/aj/Desktop/Xfinlab-main/...").
#
# Per-job disposition after auditing what's actually real:
#   - check_anomalies() -> growth/anomaly_alerts.py: REAL and now LIVE --
#     migrated into backend/main.py's actual BackgroundScheduler (30-min
#     interval, id="watchlist_anomaly_check"). This file's copy is now
#     redundant.
#   - push_channel / push_zh_channel / push_es_channel: call
#     growth/channel_push.py, growth/channel_push_zh.py,
#     growth/channel_push_es.py -- none of these three files exist in the
#     repo (only an empty growth/channel_push_all.py, 0 bytes). Would have
#     failed even if this script were run manually. The real, working
#     Telegram push is services/telegram_push_service.py, already wired
#     into api/market_pulse.py's daily free-signals job.
#   - run_email_sequences() -> services/email_sequences.py: that service's
#     DB_PATH points at backend/xfinlab.db, but the real database lives at
#     the repo root (xfinlab.db) per services/watchlist_service.py /
#     services/push_service.py -- a second, independent bug. There's also
#     no real trigger logic anywhere (no query for "users who signed up
#     exactly 1/3/7 days ago and haven't been sent this sequence yet"),
#     just the email-composition methods. Needs real design work, not a
#     quick migration -- left as-is, flagged here rather than silently
#     wired up broken.
#   - generate_fb_content() -> growth/media/facebook_generator.py: content
#     generation only, no auto-posting; more naturally a human-in-the-loop
#     marketing tool than something that should run unattended. Left as-is.
#   - daily_analysis() / weekly_report(): daily_analysis just prints 5
#     hardcoded tickers' price+news sentiment to stdout (nothing persisted,
#     nothing user-facing) -- superseded by the real free-signals/
#     market_pulse pipeline. weekly_report() is a stub that only prints
#     "Generating weekly report..." with an inline comment admitting email
#     sending "can be added later" -- never was. Neither has real value to
#     migrate.
#
# Kept in the repo unmodified/unremoved per this project's convention of
# not deleting files without asking -- but nothing in this file should be
# assumed to be running.
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

async def run_email_sequences():
    import subprocess
    subprocess.run([
        "/Library/Developer/CommandLineTools/usr/bin/python3.9",
        "/Users/aj/Desktop/Xfinlab-main/services/email_sequences.py"
    ])

scheduler.add_job(run_email_sequences, "cron", hour=10, minute=0)

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
