from datetime import datetime, timezone

from services.watchlist_service import get_db
from services.market_data_service import MarketDataService
from engines.anomaly_engine import AnomalyEngine
from services.email_service import EmailService

market_svc = MarketDataService()


def check_watchlist_anomalies():
    """檢查所有用戶自選股的異常波動，發送通知

    2026-07-23: this used to only ever run via `python growth/scheduler.py`
    (a standalone BlockingScheduler script with hardcoded local Mac paths
    that Railway's Procfile never starts -- only `uvicorn backend.main:app`
    runs in production). That meant this whole function was dead code on
    the live site: users could add stocks to their watchlist and would
    never receive an anomaly email, no matter what happened to the price.
    Now called from backend/main.py's real BackgroundScheduler instead.

    Also fixed while wiring this up for real:
    - price_change_pct was hardcoded to 0, which made the AnomalyEngine's
      HIGH severity (requires >=2 signals) mathematically unreachable --
      only the volume-ratio signal could ever fire, capping severity at
      MEDIUM forever. Now uses the real price_change_pct market_data_service
      already computes.
    - added a once-per-user-per-ticker-per-day guard (reusing the same
      push_send_log table services/push_service.py uses for the daily
      free-signals push) so a stock stuck above the threshold across
      multiple 30-min scans doesn't re-email the same person all day.
    """
    conn = get_db()

    # 取得所有有自選股的用戶
    rows = conn.execute("""
        SELECT DISTINCT w.user_id, w.ticker, u.email, u.name
        FROM watchlist w
        JOIN users u ON w.user_id = u.id
    """).fetchall()
    conn.close()

    from services.push_service import already_sent_today, mark_sent_today
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    checked_tickers = {}
    sent_count = 0

    for row in rows:
        ticker = row["ticker"]

        # 快取已查詢過嘅 ticker 數據，避免重複請求
        if ticker not in checked_tickers:
            try:
                market = market_svc.get_stock_data(ticker)
                volume = market.get("volume", 0)
                avg_volume = market.get("avg_volume", 1)
                price_change_pct = market.get("price_change_pct", 0.0)

                result = AnomalyEngine.detect(
                    current_volume=volume,
                    average_volume=avg_volume,
                    price_change_pct=price_change_pct
                )
                checked_tickers[ticker] = {"market": market, "anomaly": result}
            except Exception as e:
                print(f"Error checking {ticker}: {e}")
                continue

        data = checked_tickers[ticker]
        anomaly = data["anomaly"]

        # 只有 HIGH severity 先發送通知，並且每人每股每日最多一封
        if anomaly["severity"] == "HIGH":
            dedup_key = f"anomaly_alert:{row['user_id']}:{ticker}"
            if already_sent_today(dedup_key, today):
                continue
            try:
                detail_parts = [a["detail"] for a in anomaly["anomalies"]]
                EmailService.send_price_alert(
                    row["email"],
                    row["name"],
                    ticker,
                    data["market"].get("price", 0),
                    "；".join(detail_parts)
                )
                mark_sent_today(dedup_key, today)
                sent_count += 1
                print(f"Sent alert: {ticker} -> {row['email']}")
            except Exception as e:
                print(f"Email error: {e}")

    print(f"Anomaly check complete. {sent_count} alerts sent.")
    return sent_count


if __name__ == "__main__":
    check_watchlist_anomalies()
