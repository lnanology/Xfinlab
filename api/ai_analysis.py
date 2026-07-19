from fastapi import APIRouter
from services.market_data_service import MarketDataService
from services.news_service import NewsService
from services.technical_analysis_service import get_technical_analysis
from engines.rule_engine import RuleEngine
from engines.score_engine import ScoreEngine
from engines.risk_engine import RiskEngine
from engines.news_engine import NewsEngine
from backend.alpha.regime_detector import RegimeDetector
from services.fundamentals_service import get_fundamentals
from services.i18n import get_translations
from services.smart_beta_service import get_smart_beta

router = APIRouter()
market_svc = MarketDataService()
news_svc = NewsService()


@router.post("/ai-analysis")
async def ai_analysis(body: dict):
    from services.quota_middleware import check_token_budget, record_ai_token_usage

    symbols = body.get("symbols", [])
    filters = body.get("filters", {})
    query = body.get("query", "")
    token = body.get("token")
    lang = body.get("lang")
    # 2026-07-19 fix: the Trend/Momentum/Sentiment/Valuation/Liquidity
    # dashboard cells (and the "利好訊號"/"當前市況" summary framing on the
    # frontend) always came back in Chinese regardless of the site's
    # selected UI language -- switching to English only ever translated
    # the surrounding page chrome, never these values ("ENGLISH 重有中文").
    # Any caller that doesn't send `lang` yet keeps the exact old Chinese
    # default (zero behavior change). When a non-Chinese lang is supplied,
    # reuse the SAME idx_dir_* vocabulary already translated into all 46
    # languages for the homepage's bullish/bearish/mixed labels, instead of
    # hand-rolling a second translation table for the same 3 concepts.
    is_zh_default = not lang or lang in ("zh-HK", "zh-TW", "zh-CN")
    dir_tr = get_translations(lang) if not is_zh_default else None

    # Screener mode
    if filters and not symbols:
        from ai.ai_router import get_ai_response
        user_id = check_token_budget(token)
        prompt = (
            f"You are a stock screener AI. Based on these filters: {filters}. "
            f"Recommend 5-8 stocks with ticker, company name, reason (2 sentences), risk. "
            f"Query: {query}. Respond in Traditional Chinese."
        )
        try:
            answer = get_ai_response(prompt, max_tokens=800)
            record_ai_token_usage(user_id)
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
    # 2026-07-19 fix: was hardcoded Chinese regardless of `lang` (see the
    # is_zh_default note above the dashboard fields further down).
    if is_zh_default:
        if total_score >= 75:
            conclusion = f"{symbol} 技術面強勢，新聞情緒{news_result['sentiment']}，整體評分{total_score:.0f}/100，建議關注買入機會。"
        elif total_score >= 50:
            conclusion = f"{symbol} 整體評分{total_score:.0f}/100，市場情緒中性，建議觀望為主。"
        else:
            conclusion = f"{symbol} 整體評分{total_score:.0f}/100，技術面偏弱，建議謹慎操作。"
    else:
        if total_score >= 75:
            conclusion = f"{symbol} shows strong technicals, news sentiment {news_result['sentiment']}, overall score {total_score:.0f}/100 -- worth watching for a buying opportunity."
        elif total_score >= 50:
            conclusion = f"{symbol} overall score {total_score:.0f}/100, neutral market sentiment -- mostly a wait-and-see stance."
        else:
            conclusion = f"{symbol} overall score {total_score:.0f}/100, technicals look weak -- proceed cautiously."

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
    confluence = None
    market_structure = None
    tech_trend = None
    tech_support = None
    tech_resistance = None
    try:
        tech = get_technical_analysis(symbol)
        if tech and "error" not in tech:
            decision_levels = tech.get("decision_levels")
            confluence = tech.get("confluence")
            market_structure = tech.get("market_structure")
            tech_trend = tech.get("trend")
            tech_support = tech.get("support")
            tech_resistance = tech.get("resistance")
    except Exception:
        pass

    # ---- Layered-UX pass (2026-07-18): Hero Score / Dashboard / Accordion
    # reasons -- all derived from data this endpoint already computes above
    # (rule-engine scores, real confluence signals, real regime inputs).
    # Nothing new is fabricated; anything without a real data source
    # (valuation -- no fundamentals/multiples source exists in this
    # codebase) is honestly reported as unavailable rather than guessed.
    from datetime import datetime, timezone

    if bull >= 55 and bull >= bear:
        hero_rating = "BUY"
    elif bear >= 55 and bear > bull:
        hero_rating = "SELL"
    else:
        hero_rating = "HOLD"
    # Stars purely reflect distance-from-neutral of whichever side leads --
    # same real bull/bear numbers as the probability bars above, just
    # re-expressed as a quick-glance 1-5 scale.
    lead_pct = max(bull, bear)
    hero_stars = 1 if lead_pct < 40 else 2 if lead_pct < 55 else 3 if lead_pct < 65 else 4 if lead_pct < 80 else 5

    regime_result = None
    try:
        structure_event = None
        if market_structure and market_structure.get("events"):
            structure_event = market_structure["events"][0].get("type")
        regime_result = RegimeDetector.classify({
            "volatility": volatility,
            "trend_direction": confluence.get("direction") if confluence else None,
            "trend_confidence_pct": confluence.get("confidence_pct") if confluence else None,
            "volume_ratio": volume_ratio,
            "structure_event": structure_event,
        })
    except Exception:
        regime_result = None

    # 2026-07-18: was a hardcoded "N/A（暫無估值數據源）" -- now backed by
    # services/fundamentals_service.py's real SEC EDGAR data (US-listed
    # SEC filers only; non-US tickers/no-match honestly still report
    # unavailable, never a guessed P/E).
    fundamentals = get_fundamentals(symbol, current_price=market.get("price") or None)
    if fundamentals.get("available") and fundamentals.get("pe_ratio") is not None:
        valuation_display = f"P/E {fundamentals['pe_ratio']}"
    elif fundamentals.get("available"):
        valuation_display = "P/E 不適用（EPS為負或缺失）" if is_zh_default else "P/E N/A (negative or missing EPS)"
    else:
        valuation_display = "N/A（非美股SEC申報公司或暫無數據）" if is_zh_default else "N/A (not a US SEC-filing company, or no data available)"

    raw_trend = tech_trend or ("上升" if trend == "bullish" else "下降" if trend == "bearish" else "中性")
    raw_momentum = (confluence.get("direction") if confluence else None) or "數據不足"
    raw_sentiment = "偏多" if bull > bear else "偏空" if bear > bull else "中性"
    raw_liquidity = "偏低" if volume_ratio < 0.7 else "良好"

    if is_zh_default:
        trend_display = raw_trend
        momentum_display = raw_momentum
        sentiment_display = raw_sentiment
        liquidity_display = raw_liquidity
    else:
        # Same finite vocabulary technical_analysis_service.py / this
        # endpoint's own fallbacks return in Chinese, mapped onto the
        # already-46-language-translated idx_dir_* labels rather than a
        # second hand-rolled table for the same bullish/bearish/neutral
        # concepts.
        dir_map = {
            "上升": dir_tr.get("idx_dir_bull", "Bullish"),
            "下降": dir_tr.get("idx_dir_bear", "Bearish"),
            "中性": dir_tr.get("idx_dir_neutral", "Mixed, Neutral"),
            "偏多": dir_tr.get("idx_dir_bull", "Bullish"),
            "偏空": dir_tr.get("idx_dir_bear", "Bearish"),
            "訊號分歧，中性": dir_tr.get("idx_dir_neutral", "Mixed, Neutral"),
            "數據不足": dir_tr.get("idx_dir_insufficient", "Insufficient data"),
        }
        trend_display = dir_map.get(raw_trend, raw_trend)
        momentum_display = dir_map.get(raw_momentum, raw_momentum)
        sentiment_display = dir_map.get(raw_sentiment, raw_sentiment)
        liquidity_display = "Low" if raw_liquidity == "偏低" else "Good"

    dashboard = {
        "trend": trend_display,
        "risk": risk_result["risk_level"],
        "momentum": momentum_display,
        "news": news_result["sentiment"],
        "sentiment": sentiment_display,
        "valuation": valuation_display,
        "liquidity": liquidity_display,
    }

    reasons = {
        "bullish": (confluence.get("bullish_signals") if confluence else []) or [],
        "bearish": (confluence.get("bearish_signals") if confluence else []) or [],
    }

    # ---- Tier 2: Scenario Lab (Bull/Base/Bear) ----
    # Targets reuse decision_levels' real ATR/support-resistance-derived
    # TP1/TP3/stop -- never invented price levels. Probabilities are
    # deterministically derived from confluence's real confidence_pct
    # (signal-agreement strength), NOT a statistical forecast -- labelled
    # honestly via `methodology` so nobody mistakes this for a calibrated
    # probability model the way api/pipeline_api.py already cautions for
    # its own bullish_probability field.
    scenario = None
    if decision_levels and confluence:
        conf_pct = confluence.get("confidence_pct", 0) or 0
        bias = decision_levels["bias"]
        tp1, _, tp3 = decision_levels["take_profits"]
        stop = decision_levels["stop_loss"]
        base_prob = round(min(70, max(30, 30 + conf_pct * 0.4)))
        remaining = 100 - base_prob
        trend_prob = round(remaining * (0.5 + conf_pct / 200))
        trend_prob = min(remaining, max(0, trend_prob))
        counter_prob = remaining - trend_prob
        if bias == "long":
            scenario = {
                "bull": {"target": tp3, "probability_pct": trend_prob},
                "base": {"target": tp1, "probability_pct": base_prob},
                "bear": {"target": stop, "probability_pct": counter_prob},
            }
        else:
            scenario = {
                "bull": {"target": stop, "probability_pct": counter_prob},
                "base": {"target": tp1, "probability_pct": base_prob},
                "bear": {"target": tp3, "probability_pct": trend_prob},
            }
        scenario["methodology"] = (
            "機率粗略推算自現時訊號共識程度（Confluence confidence），"
            "並非統計預測模型，僅供參考，並非投資建議。"
        )

    # Stage 1 roadmap (2026-07-19): Smart Beta multi-factor score + the
    # Bayesian regime-probability update that drives its dynamic factor
    # weighting -- see services/smart_beta_service.py. Independently
    # try/except'd so a failure here (e.g. this symbol's fundamentals
    # genuinely unavailable) never breaks the rest of an otherwise
    # working analysis.
    try:
        smart_beta = get_smart_beta(symbol, current_price=market.get("price"))
    except Exception:
        smart_beta = None

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
            "decision_levels": decision_levels,
            "hero": {
                "rating": hero_rating,
                "stars": hero_stars,
                "confidence_pct": (confluence.get("confidence_pct") if confluence else None) or lead_pct,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
            "dashboard": dashboard,
            "regime": regime_result,
            "reasons": reasons,
            "support_resistance": {
                "support": tech_support,
                "resistance": tech_resistance,
            },
            "scenario": scenario,
            # News Timeline (Tier 2): the SAME real headlines already
            # fetched above for news_result -- just passed through with
            # their url/published_at instead of only the aggregate score.
            "news_headlines": news[:8],
            "fundamentals": fundamentals,
            "smart_beta": smart_beta,
        }
    }
