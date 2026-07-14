from fastapi import APIRouter
from services.market_data_service import MarketDataService
from services.news_service import NewsService
from services.technical_analysis_service import get_technical_analysis
from engines.rule_engine import RuleEngine
from engines.score_engine import ScoreEngine
from engines.risk_engine import RiskEngine
from engines.news_engine import NewsEngine

router = APIRouter()
market_svc = MarketDataService()
news_svc = NewsService()


@router.post("/ai-analysis")
async def ai_analysis(body: dict):
    symbols = body.get("symbols", [])
    filters = body.get("filters", {})
    query = body.get("query", "")

    # Screener mode
    if filters and not symbols:
        from ai.ai_router import get_ai_response
        prompt = (
            f"You are a stock screener AI. Based on these filters: {filters}. "
            f"Recommend 5-8 stocks with ticker, company name, reason (2 sentences), risk. "
            f"Query: {query}. Respond in Traditional Chinese."
        )
        try:
            answer = get_ai_response(prompt, max_tokens=800)
        except:
            answer = "篩選服務暫時不可用，請稍後再試。"
        return {"status": "ok", "data": {"conclusion": answer, "analysis": answer}}

    if not symbols:
        return {"status": "ok", "data": {}}

    symbol = symbols[0].upper()

    # Market data
    market = market_svc.get_stock_data(symbol)
    volume_ratio = market.get("volume_ratio", 1.0)
    trend = market.get("trend", "neutral")
    breakout = market.get("breakout", False)
    sentiment = market.get("sentiment", "neutral")

    # Rule engine
    rule_engine = RuleEngine()
    rule_scores = rule_engine.evaluate({
        "volume_ratio": volume_ratio,
        "trend": trend,
        "breakout": breakout,
        "sentiment": sentiment
    })

    # Score engine
    score_engine = ScoreEngine()
    score_result = score_engine.calculate(rule_scores)
    total_score = score_result["total_score"]

    # News
    news = news_svc.get_company_news(symbol)
    news_result = NewsEngine.analyze([
        {"title": a["title"], "summary": a["title"]}
        for a in news[:5]
    ])
    news_score = news_result["score"]

    # Risk
    volatility = volume_ratio * 15
    risk_result = RiskEngine.calculate(
        volatility=volatility,
        event_risk=20,
        news_score=news_score
    )
    risk_score = risk_result["overall_risk"]

    # Scores
    fund_score = min(100, round(total_score * 0.8 + news_score * 0.2, 1))
    tech_score = min(100, round(total_score, 1))
    news_score_out = round(news_score, 1)
    risk_score_out = round(100 - risk_score, 1)

    # Probabilities
    bull = min(90, max(10, round(total_score)))
    bear = min(80, max(5, round(100 - total_score - 10)))
    flat = max(5, 100 - bull - bear)

    # Risks
    risks = []
    if risk_result["risk_level"] == "HIGH":
        risks.append({"title": "高風險警告", "desc": "市場波動較大，需謹慎操作"})
    if volume_ratio < 0.5:
        risks.append({"title": "成交量偏低", "desc": "流動性不足，難以大量進出"})
    if trend == "bearish":
        risks.append({"title": "下降趨勢", "desc": "價格處於下降通道，注意止損"})
    if not risks:
        risks.append({"title": "風險可控", "desc": "目前市場狀況相對穩定"})

    # Conclusion
    if total_score >= 75:
        conclusion = f"{symbol} 技術面強勢，新聞情緒{news_result['sentiment']}，整體評分{total_score:.0f}/100，建議關注買入機會。"
    elif total_score >= 50:
        conclusion = f"{symbol} 整體評分{total_score:.0f}/100，市場情緒中性，建議觀望為主。"
    else:
        conclusion = f"{symbol} 整體評分{total_score:.0f}/100，技術面偏弱，建議謹慎操作。"

    # Phase 1 wiring: this endpoint has always used its own lightweight
    # rule/score engine (volume_ratio/trend/breakout/sentiment above) for
    # the fund/tech/news/risk scores and bull/flat/bear split -- that part
    # is unchanged. Real Entry/Stop/TP/Risk-Reward levels need actual
    # support/resistance/ATR from historical price data, which this
    # endpoint never computed, so they're pulled in here from the SAME
    # shared technical_analysis_service used by chart-analysis.html,
    # market_pulse.py, hero_showcase.py etc. Purely additive: if the
    # symbol isn't tradeable/has insufficient history, decision_levels is
    # simply None and the frontend renders nothing extra (never a
    # fabricated level).
    decision_levels = None
    try:
        tech = get_technical_analysis(symbol)
        if tech and "error" not in tech:
            decision_levels = tech.get("decision_levels")
    except Exception:
        decision_levels = None

    return {
        "data": {
            "scores": {
                "fund": fund_score,
                "tech": tech_score,
                "news": news_score_out,
                "risk": risk_score_out
            },
            "probabilities": {
                "bull": bull,
                "flat": flat,
                "bear": bear
            },
            "risks": risks,
            "conclusion": conclusion,
            "symbol": symbol,
            "price": market.get("price", 0),
            "decision_levels": decision_levels
        }
    }
