
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
import numpy as np
import yfinance as yf
from fastapi import APIRouter

from core.master_pipeline import MasterPipeline
from services.market_data_service import get_stock_data
from services.technical_analysis_service import get_technical_analysis
from services.news_service import NewsService

router = APIRouter()
logger = logging.getLogger(__name__)

# 呢個endpoint之前用緊hardcoded mock data(唔理你查邊隻股票,input都係一樣),
# MasterPipeline入面17個module(quant/alpha/trading/evolution/agents/agi)嘅
# 公式本身冇經過回測/校準,只係簡單嘅weighted formula。接返真實數據之後,
# 呢啲formula嘅"準確度"依然未經驗證 —— 所以刻意唔顯示BUY/SELL/STRONG BUY
# 呢啲好似專業建議嘅字眼,淨係用「機率」框架顯示,避免俾人誤會呢個係已驗證
# 嘅投資建議。


def _price_series(ticker: str, period: str = "3mo"):
    try:
        hist = yf.Ticker(ticker).history(period=period, interval="1d")
        if hist is None or hist.empty:
            return None
        return hist["Close"].tolist()
    except Exception as e:
        logger.info("pipeline_api: price history fetch failed for %s: %s", ticker, e)
        return None


def _realized_volatility_0_100(prices):
    """粗略年化波幅,壓縮做0-100分,俾RiskAgent用。"""
    if not prices or len(prices) < 2:
        return 50.0  # 數據唔夠,用中性值,唔假裝準確
    arr = np.array(prices, dtype=float)
    returns = np.diff(arr) / arr[:-1]
    if len(returns) == 0 or np.std(returns) == 0:
        return 50.0
    annualized = float(np.std(returns) * np.sqrt(252) * 100)
    return round(min(100.0, annualized), 1)


def _fetch_real_pipeline_inputs(ticker: str):
    """
    將真實市場數據砌成MasterPipeline.run()要嘅market_data/news_data形狀。
    每一步都有fallback,任何一個數據源攞唔到都唔會累到成個pipeline爆,
    退返做中性/保守嘅預設值。
    """
    tech = get_technical_analysis(ticker)
    tech_ok = isinstance(tech, dict) and "error" not in tech

    snapshot = get_stock_data(ticker)
    snapshot_ok = isinstance(snapshot, dict) and "error" not in snapshot

    prices = _price_series(ticker) or [100.0, 101.0, 102.0]
    volatility = _realized_volatility_0_100(prices)

    news_data = []
    try:
        news_data = NewsService().get_company_news(ticker)
    except Exception as e:
        # NEWS_API_KEY未set,或者request失敗 —— 兩者都退返做冇新聞,
        # NewsAgent對冇新聞嘅情況已經有中性fallback(score=50)。
        logger.info("pipeline_api: news fetch unavailable for %s: %s", ticker, e)

    confluence = tech.get("confluence", {}) if tech_ok else {}
    confluence_score = confluence.get("score", 0)
    score_0_100 = round((confluence_score + 100) / 2, 1)

    # Step 2 of the Strategy Intelligence roadmap (2026-07-18): these three
    # were already being computed by TechnicalAnalysisService (Confluence
    # Engine's direction/confidence_pct, and volume_ratio) but never passed
    # into market_data, so RegimeDetector could only ever see `volatility`.
    # structure_event pulls the single most recent Market Structure Engine
    # event (if any) so RegimeDetector can flag TREND_REVERSAL_WATCH on a
    # real CHOCH rather than guessing.
    trend_direction = confluence.get("direction") if tech_ok else None
    trend_confidence_pct = confluence.get("confidence_pct") if tech_ok else None
    volume_ratio = tech.get("volume_ratio") if tech_ok else None
    market_structure = tech.get("market_structure") if tech_ok else None
    structure_event = None
    if market_structure and market_structure.get("events"):
        structure_event = market_structure["events"][0].get("type")

    # market_link矩陣:呢隻股vs大盤(SPY)嘅相關性,俾TensorNetwork用。
    # 攞唔到就退返做2x3嘅中性矩陣(即係之前嗰個mock預設值)。
    matrix = [[1, 2, 3], [2, 3, 4]]
    spy_prices = _price_series("SPY")
    if spy_prices and len(spy_prices) > 2:
        n = min(len(prices), len(spy_prices))
        if n > 2:
            matrix = [prices[-n:], spy_prices[-n:]]

    price = (
        snapshot.get("price") if snapshot_ok and snapshot.get("price") else None
    ) or (tech.get("last_close") if tech_ok else None) or 100.0

    market_data = {
        "score": score_0_100,
        "price": price,
        "volatility": volatility,
        # 冇專門嘅即時event-risk數據源,用中性值50,唔假裝有分析過
        # 突發事件風險 —— database/event_history table淨係得歷史pattern,
        # 未接駁做real-time feed。
        "event_risk": 50,
        "volume": snapshot.get("volume", 0) if snapshot_ok else 0,
        "prices": prices,
        "matrix": matrix,
        # Step 2 additions -- real Confluence/Market Structure Engine
        # outputs, feeding RegimeDetector's multi-factor classification
        # (see backend/alpha/regime_detector.py).
        "trend_direction": trend_direction,
        "trend_confidence_pct": trend_confidence_pct,
        "volume_ratio": volume_ratio,
        "structure_event": structure_event,
    }
    return market_data, news_data, {"tech_ok": tech_ok, "snapshot_ok": snapshot_ok}


def _to_probability_view(raw: dict, data_quality: dict) -> dict:
    """
    將MasterPipeline嘅內部verdict/signal(BUY/SELL/STRONG BUY呢啲)轉做
    機率百分比顯示,唔對外顯示任何「建議」字眼 —— 呢批公式未經回測校準,
    唔應該扮專業投資建議。
    """
    final_score = raw.get("decision", {}).get("final_score", 50)
    bullish_probability = round(max(0.0, min(100.0, final_score)) / 100, 3)

    # regime係"STRONG_BULLISH"/"PANIC"呢類市況描述,唔係買賣建議,所以OK
    # 擺出嚟。Committee.vote()就係直接返BUY/SELL/HOLD呢隻string —— 呢個
    # 先係user明確話唔想顯示嘅嘢,所以刻意唔攞嚟用。
    #
    # Step 2 of the Strategy Intelligence roadmap (2026-07-18): expanded
    # from 3 volatility-only buckets to RegimeDetector's 9-state taxonomy
    # (see backend/alpha/regime_detector.py) -- kept the old 3 keys too so
    # this stays backward compatible if `regime` is ever "NORMAL" etc.
    # from some other caller.
    regime_zh = {
        "STRONG_BULLISH": "強勢多頭",
        "WEAK_BULLISH": "弱勢多頭",
        "STRONG_BEARISH": "強勢空頭",
        "WEAK_BEARISH": "弱勢空頭",
        "RANGING": "區間震盪",
        "HIGH_VOLATILITY": "高波動",
        "PANIC": "恐慌",
        "EUPHORIA": "狂熱",
        "LOW_LIQUIDITY": "流動性不足",
        "LOW_VOLATILITY": "低波動",
        "NORMAL": "正常波動",
    }.get(raw.get("regime"), "未知")

    secondary_flag_zh = {
        "LOW_LIQUIDITY": "流動性不足",
        "TREND_REVERSAL_WATCH": "疑似轉勢，觀察中",
    }
    regime_secondary_flags_zh = [
        secondary_flag_zh.get(f, f) for f in raw.get("regime_secondary_flags", [])
    ]

    return {
        "ticker": raw["ticker"],
        "bullish_probability": bullish_probability,
        "bearish_probability": round(1 - bullish_probability, 3),
        "market_regime": regime_zh,
        "market_regime_flags": regime_secondary_flags_zh,
        "risk_score": raw.get("risk", {}).get("risk_score"),
        "risk_level": raw.get("risk", {}).get("level"),
        "factor_score": raw.get("factor", {}).get("factor_score"),
        "news_sentiment_score": raw.get("news", {}).get("score"),
        "market_correlation": raw.get("tensor", {}).get("market_link"),
        "data_quality": data_quality,
        "disclaimer": "以上機率由未經歷史回測校準嘅內部公式計算，僅供參考，並非投資建議。",
    }


@router.get("/pipeline/{ticker}")
def run_pipeline(ticker: str):
    ticker = ticker.upper()
    market_data, news_data, data_quality = _fetch_real_pipeline_inputs(ticker)
    raw = MasterPipeline.run(ticker, market_data, news_data)
    return _to_probability_view(raw, data_quality)
