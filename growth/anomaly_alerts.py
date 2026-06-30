import os
import sys
sys.path.insert(0, "/Users/aj/Desktop/Xfinlab-main")

from services.watchlist_service import get_db
from services.market_data_service import MarketDataService
from engines.anomaly_engine import AnomalyEngine
from services.email_service import EmailService

market_svc = MarketDataService()


def check_watchlist_anomalies():
    """檢查所有用戶自選股的異常波動，發送通知"""
    conn = get_db()
    
    # 取得所有有自選股的用戶
    rows = conn.execute("""
        SELECT DISTINCT w.user_id, w.ticker, u.email, u.name
        FROM watchlist w
        JOIN users u ON w.user_id = u.id
    """).fetchall()
    conn.close()

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
                
                # 簡化：用 volume ratio 同模擬 price change 偵測異常
                volume_ratio = volume / avg_volume if avg_volume > 0 else 1
                price = market.get("price", 0)
                
                result = AnomalyEngine.detect(
                    current_volume=volume,
                    average_volume=avg_volume,
                    price_change_pct=0  # 需要歷史價格比較，簡化處理
                )
                checked_tickers[ticker] = {"market": market, "anomaly": result}
            except Exception as e:
                print(f"Error checking {ticker}: {e}")
                continue

        data = checked_tickers[ticker]
        anomaly = data["anomaly"]

        # 只有 HIGH severity 先發送通知
        if anomaly["severity"] == "HIGH":
            try:
                EmailService.send_price_alert(
                    row["email"],
                    row["name"],
                    ticker,
                    data["market"].get("price", 0),
                    f"成交量異常：{anomaly['volume_ratio']}x 平均成交量"
                )
                sent_count += 1
                print(f"Sent alert: {ticker} -> {row['email']}")
            except Exception as e:
                print(f"Email error: {e}")

    print(f"Anomaly check complete. {sent_count} alerts sent.")
    return sent_count


if __name__ == "__main__":
    check_watchlist_anomalies()
