from fastapi import APIRouter
from services.market_data_service import MarketDataService
from services.news_service import NewsService
from services.technical_analysis_service import get_technical_analysis_raw_and_translated
from engines.rule_engine import RuleEngine
from engines.score_engine import ScoreEngine
from engines.risk_engine import RiskEngine
from engines.news_engine import NewsEngine
from backend.alpha.regime_detector import RegimeDetector
from services.fundamentals_service import get_fundamentals
from services.i18n import get_translations, ai_language_instruction
from services.smart_beta_service import get_smart_beta
from services.fractal_regime_service import detect_transition_signal as detect_fractal_transition
from services.direction_probability_service import get_direction_probability
from services.shipping_proxy_service import get_shipping_proxy

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

    # 2026-07-26 product decision: Smart Beta / Scenario Lab / Market Regime
    # probability are "advanced engine" fields reserved for Pro tier and
    # above (see services/quota_middleware.py's ADVANCED_ENGINE_PLANS).
    # Computed as normal below regardless of plan (so a gating bug here can
    # never break the rest of an otherwise-working analysis for anyone),
    # then swapped for a locked placeholder just before the response is
    # returned -- Free/Basic users still get the full core analysis
    # (dashboard/hero/fundamentals/etc.), only these 3 fields are redacted.
    from services.quota_middleware import is_advanced_engine_plan
    is_pro_plan = is_advanced_engine_plan(token)
    _locked_advanced_engine = {
        "locked": True,
        "required_plan": "pro",
        "upgrade_url": "https://xfinlab.com/pricing.html",
    }

    # Screener mode
    if filters and not symbols:
        from ai.ai_router import get_ai_response
        user_id = check_token_budget(token)
        # 2026-07-23 fix (task #317/#327): this always hard-forced
        # "Respond in Traditional Chinese." regardless of `lang` -- unlike
        # api/chat.py (which already used ai_language_instruction), the
        # screener ignored the UI's selected language entirely, so an
        # English-mode user still got a Chinese screening result. Reuses
        # the exact same helper chat.py uses, keyed off the same `lang`
        # the frontend already sends everywhere else.
        prompt = (
            f"You are a stock screener AI. Based on these filters: {filters}. "
            f"Recommend 5-8 stocks with ticker, company name, reason (2 sentences), risk. "
            f"Query: {query}. {ai_language_instruction(lang)}"
        )
        try:
            answer = get_ai_response(prompt, max_tokens=800)
            record_ai_token_usage(user_id)
        except Exception:
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
    # 2026-07-25 fix: this was the only one of this endpoint's ~8 external
    # data calls NOT wrapped in try/except (smart_beta, direction_probability,
    # shipping_proxy, hurst_signal, regime_result, tech are all guarded a few
    # lines below) -- NewsService only catches requests.RequestException
    # internally, so any other failure (e.g. a malformed/rate-limited
    # response body) would propagate all the way up and 500 the whole
    # analysis for an otherwise-fine symbol. Falling back to an empty list
    # matches NewsService's own "network failed" behavior.
    try:
        news = news_svc.get_company_news(symbol)
    except Exception:
        news = []
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
    confluence_raw = None
    market_structure = None
    tech_trend = None
    tech_support = None
    tech_resistance = None
    tech_ohlc = None
    tech_raw = None
    data_warning = None
    try:
        # 2026-07-25 fix (task #409): pass lang through so the confluence
        # engine's dynamic signal strings (bullish_signals/bearish_signals,
        # feeding this page's "reasons"/decision-report content) translate
        # the same way the dashboard fields a few lines below already do,
        # instead of leaking raw Chinese into an English-mode page.
        #
        # 2026-07-25 fix (task #412): switched from get_technical_analysis()
        # to get_technical_analysis_raw_and_translated(), which returns BOTH
        # the translated dict (`tech`, used for display exactly as before)
        # AND the untranslated original (`tech_raw`). Two things downstream
        # -- RegimeDetector.classify()'s trend_direction and, via
        # get_smart_beta(), regime_belief_service.py's evidence scoring --
        # do an exact-match comparison against the Chinese literals
        # '偏多'/'偏空'. Feeding them the translated ("Bullish"/"Bearish")
        # value silently broke both (always scoring/classifying neutral)
        # for every non-Chinese-language request since task #409 shipped --
        # a real regression, not a hypothetical one. `tech_raw` fixes that
        # without a second network fetch.
        tech_raw, tech = get_technical_analysis_raw_and_translated(symbol, lang=lang)
        if tech and "error" not in tech:
            decision_levels = tech.get("decision_levels")
            confluence = tech.get("confluence")
            market_structure = tech.get("market_structure")
            tech_trend = tech.get("trend")
            tech_support = tech.get("support")
            tech_resistance = tech.get("resistance")
            # 2026-07-25 ("自行建可顯示任何資產嘅K線圖，不用TradingView"):
            # this was already being fetched for decision_levels/confluence
            # above -- just wasn't forwarded to the frontend before, since
            # this page only ever showed the TradingView iframe (which
            # needs no OHLC data of its own). Now that ai-analysis.html
            # draws its own candlestick chart, it needs the same real bars.
            tech_ohlc = tech.get("ohlc")
        elif tech and "error" in tech:
            # 2026-07-30 fix ("查0544 出唔到股票"): technical_analysis_
            # service.py's own get_analysis() already returns an honest
            # "{symbol} 歷史數據不足，無法計算技術指標" message when a
            # thinly-traded ticker (e.g. 0544.HK / Daido Group -- real,
            # listed, but very low trading volume) has fewer than 20 days
            # of usable OHLC history -- correct behavior, not a bug (this
            # codebase never fabricates indicators from insufficient data).
            # The bug was that this message was computed and then silently
            # dropped: the frontend just hid the chart panel with zero
            # explanation, which reads exactly like "查唔到" to a user even
            # though the search itself worked fine and other sections
            # (price/fundamentals/scores below) still render normally.
            # Forwarding it through so ai-analysis.html can show an honest
            # one-line reason instead of an unexplained gap.
            data_warning = tech.get("error")
        if tech_raw and "error" not in tech_raw:
            confluence_raw = tech_raw.get("confluence")
    except Exception:
        pass

    # ---- Layered-UX pass (2026-07-18): Hero Score / Dashboard / Accordion
    # reasons -- all derived from data this endpoint already computes above
    # (rule-engine scores, real confluence signals, real regime inputs).
    # Nothing new is fabricated; anything without a real data source
    # (valuation -- no fundamentals/multiples source exists in this
    # codebase) is honestly reported as unavailable rather than guessed.
    from datetime import datetime, timezone

    # 2026-07-23 note (platform audit finding): this BUY/SELL/HOLD label is
    # a THIRD, independent rating vocabulary/threshold set, separate from
    # engines/decision_engine.py's DecisionEngine (Strong Buy/Bullish/
    # Neutral/Bearish) and engines/scoring_engine.py's ScoringEngine
    # (Strong Buy/Buy/Neutral/Sell/Strong Sell) used by
    # api/full_analysis_v3.py. All three are live/reachable simultaneously.
    # Not unified here on purpose: this page (ai-analysis.html) is the
    # most-visited analysis surface, so changing its rating thresholds is a
    # product decision that changes what real users see today, not a pure
    # refactor -- needs explicit sign-off before merging.
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

    # 2026-07-19 Stage 2 roadmap ("市況轉換偵測延伸"): a real Hurst-exponent
    # transition read, wrapped in its own try/except so a slow/failed
    # extra history fetch never breaks the regime classification (or the
    # rest of the analysis) it's merely annotating.
    hurst_signal = None
    try:
        hurst_signal = detect_fractal_transition(symbol)
    except Exception:
        hurst_signal = None

    regime_result = None
    try:
        structure_event = None
        if market_structure and market_structure.get("events"):
            structure_event = market_structure["events"][0].get("type")
        # 2026-07-25 fix (task #412): use confluence_raw (untranslated),
        # not `confluence` -- RegimeDetector.classify() exact-matches
        # trend_direction against the Chinese literals '偏多'/'偏空' (see
        # backend/alpha/regime_detector.py); feeding it the English-
        # translated value silently classified every non-Chinese request
        # as neutral/RANGING regardless of the real signal.
        regime_result = RegimeDetector.classify({
            "volatility": volatility,
            "trend_direction": confluence_raw.get("direction") if confluence_raw else None,
            "trend_confidence_pct": confluence_raw.get("confidence_pct") if confluence_raw else None,
            "volume_ratio": volume_ratio,
            "structure_event": structure_event,
            "hurst_signal": hurst_signal,
        })
    except Exception:
        regime_result = None

    # 2026-07-18: was a hardcoded "N/A（暫無估值數據源）" -- now backed by
    # services/fundamentals_service.py's real SEC EDGAR data (US-listed
    # SEC filers only; non-US tickers/no-match honestly still report
    # unavailable, never a guessed P/E).
    # 2026-07-25 fix: same "only unguarded external call" issue as the news
    # fetch above -- get_fundamentals() is internally safe against network
    # failures, but wrapping it here too means a future change inside it can
    # never take down this whole endpoint for a symbol it doesn't recognize.
    try:
        fundamentals = get_fundamentals(symbol, current_price=market.get("price") or None)
    except Exception:
        fundamentals = {"status": "error", "available": False, "message": "暫時無法取得估值數據"}
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
        # 2026-07-25 fix (task #412): pass the already-fetched tech_raw/
        # fundamentals through instead of letting get_smart_beta() re-fetch
        # both from scratch (plus a third redundant OHLC-history fetch it
        # used to do internally for the exact same symbol/period/interval)
        # -- see services/smart_beta_service.py's docstring. Deliberately
        # `tech_raw` (untranslated), not the display `tech`: get_smart_beta
        # feeds confluence.direction into services/regime_belief_service.py,
        # which -- like RegimeDetector.classify() above -- exact-matches
        # against the Chinese '偏多'/'偏空' literals. get_smart_beta's own
        # response never surfaces that raw confluence text to the user
        # (its factor labels are fixed English strings), so using the
        # untranslated version here is both correct and safe.
        smart_beta = get_smart_beta(
            symbol,
            current_price=market.get("price"),
            tech=tech_raw,
            fundamentals=fundamentals,
        )
    except Exception:
        smart_beta = None

    # Stage 2 roadmap (2026-07-19): lightweight scikit-learn direction-
    # probability model (see services/direction_probability_service.py
    # for why this is scikit-learn rather than a literal LSTM, and for
    # the backtest significance gate that must pass before a symbol's
    # model is ever served here). Only ever returns a prediction for
    # symbols whose model has already been trained+validated by
    # scripts/train_direction_models.py -- this endpoint never trains
    # on the fly, and honestly reports unavailable otherwise.
    try:
        direction_probability = get_direction_probability(symbol)
    except Exception:
        direction_probability = None

    # Stage 3 roadmap (2026-07-20): real market-based shipping/supply-chain
    # proxy (BDRY/BOAT ETF prices) -- see services/shipping_proxy_service.py
    # for why this is a labeled proxy, not the official Baltic Dry Index.
    # Market-wide, not symbol-specific -- same value surfaces regardless of
    # which symbol is being analyzed, cached internally to avoid refetching
    # on every request.
    try:
        shipping_proxy = get_shipping_proxy()
    except Exception:
        shipping_proxy = None

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
            "ohlc": tech_ohlc,
            "data_warning": data_warning,
            "hero": {
                "rating": hero_rating,
                "stars": hero_stars,
                "confidence_pct": (confluence.get("confidence_pct") if confluence else None) or lead_pct,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
            "dashboard": dashboard,
            "regime": regime_result if is_pro_plan else _locked_advanced_engine,
            "reasons": reasons,
            "support_resistance": {
                "support": tech_support,
                "resistance": tech_resistance,
            },
            "scenario": scenario if is_pro_plan else _locked_advanced_engine,
            # News Timeline (Tier 2): the SAME real headlines already
            # fetched above for news_result -- just passed through with
            # their url/published_at instead of only the aggregate score.
            "news_headlines": news[:8],
            "fundamentals": fundamentals,
            "smart_beta": smart_beta if is_pro_plan else _locked_advanced_engine,
            "direction_probability": direction_probability,
            "shipping_proxy": shipping_proxy,
        }
    }
