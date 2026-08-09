"""
Research Agency -- 2026-08-09, XFINLAB_Final_Strategy.md section 6/7
("agency-swarm起多角度research功能", P2).

What "agency-swarm" actually contributed here: agency-swarm (VRSEN, MIT
licence) is a multi-agent orchestration pattern -- an Agency composed of
several Agents, each with a defined role and its own tools, that hand off
work in a defined sequence rather than one monolithic prompt trying to
do everything. The package itself is built specifically on OpenAI's
Assistants API (threads/runs) -- pulling it in as a dependency would mean
adding the `openai` SDK plus its own orchestration runtime to a
single-dyno Railway app that has zero other OpenAI-API usage anywhere in
this codebase (every AI call in ai/ai_router.py goes through DeepSeek/
DeepInfra/Groq/Claude instead). That's the same tradeoff already made
for every other external SDK this session (services/youtube_upload_
service.py over google-api-python-client, api/mcp_server.py over the
`mcp` PyPI package): the ARCHITECTURE is worth adopting, the SDK is not,
per this project's standing "keep go build" rule.

So this module hand-rolls the agency-swarm PATTERN on top of the
existing ai/ai_router.py plumbing:

  Stage 1 -- Data-gathering agents (real function calls, zero LLM calls,
  zero fabrication risk): each "agent" here is just a real service call
  against a specific domain of already-built, already-verified data:
    - technical_analyst  -> services/technical_analysis_service.py
    - news_analyst       -> services/rss_news_service.py +
                             services/finbert_sentiment_service.py
    - macro_analyst      -> services/world_engine_service.py (World
                             Engine Phase 0, shipped earlier this session
                             -- this is the first consumer of that work)
    - fundamentals_analyst -> services/fundamentals_service.py

  Stage 2 -- Debate agents (LLM calls, DeepSeek via ai_router, same
  provider/cost posture as services/agent_debate_service.py): Bull/Bear/
  Risk Manager, each instructed to argue ONLY from the Stage-1 data
  actually gathered, never invent a number not present in the summary.

  Stage 3 -- Arbiter: synthesizes the 3 debate arguments into a verdict,
  same constraint (no new data, only commentary on what was already said).

This is a genuinely richer "multi-angle" upgrade over services/
agent_debate_service.py's existing run_debate(), which only argues from
whatever confluence/regime/decision_levels the CALLER already had on
hand (api/agent_debate.py builds a fairly thin context from one
technical-analysis call). This module is self-sufficient: given just a
ticker, it gathers technical + news/sentiment + macro + fundamentals
itself before any debate agent speaks, then debates over that fuller
picture. It does NOT replace agent_debate_service.py (kept as the
cheaper, faster single-context debate any page can still call) --
this is the deeper, slower "run a proper multi-angle research pass"
option, one tier up in cost.

Honesty contract (same standard as every module this session): each
Stage-1 gather either succeeds with real data or is honestly marked
unavailable in the summary handed to the debate agents -- a debate
agent is explicitly told which angles have no data ("暫無") so it never
improvises a number for a domain that came back empty. Never a
directional trading signal or probability estimate at any stage -- same
standing compliance line as agent_debate_service.py and the rest of this
codebase.
"""

import logging
import os
from typing import Dict, Optional

from ai import ai_router
from ai.ai_router import get_ai_response
from services.i18n import ai_language_instruction

logger = logging.getLogger(__name__)

_PROVIDER = "deepseek"
_MAX_TOKENS = 300

# Same key as agent_debate_service.py -- both features are DeepSeek-only
# for the same cost/latency reasons documented there.
def is_available() -> bool:
    return bool(os.getenv("DEEPINFRA_API_KEY"))


# Crude ticker-suffix -> World Engine region guess. Deliberately simple
# and honestly a heuristic (documented, not hidden) -- good enough to
# pick a genuinely relevant macro region for the vast majority of
# tickers this site actually sees (US-suffixless, .HK, .TW being the
# 3 most common), defaults to "us" rather than guessing wrong silently
# for an exotic suffix this map doesn't cover.
_SUFFIX_TO_REGION = {
    "HK": "hk", "TW": "tw", "KS": "korea", "KQ": "korea",
    "SS": "china", "SZ": "china", "SI": "sea",
    "SA": "latam", "SR": "me",
    "L": "europe", "PA": "europe", "DE": "europe", "AS": "europe", "MI": "europe",
}


def _guess_region(symbol: str) -> str:
    parts = (symbol or "").upper().split(".")
    if len(parts) == 2:
        return _SUFFIX_TO_REGION.get(parts[1], "us")
    return "us"


def _gather_technical(symbol: str) -> Optional[Dict]:
    try:
        from services.technical_analysis_service import get_technical_analysis
        tech = get_technical_analysis(symbol)
        if not tech or "error" in tech:
            return None
        confluence = tech.get("confluence") or {}
        return {
            "direction": confluence.get("direction"),
            "confidence_pct": confluence.get("confidence_pct"),
            "bullish_signals": confluence.get("bullish_signals") or [],
            "bearish_signals": confluence.get("bearish_signals") or [],
            "regime": (tech.get("market_structure") or {}).get("regime"),
        }
    except Exception as e:
        logger.info("research_agency_service: technical_analyst failed for %s: %s", symbol, e)
        return None


def _gather_news_sentiment(symbol: str) -> Optional[Dict]:
    try:
        from services.rss_news_service import search_headlines
        from services.finbert_sentiment_service import analyze_batch, is_available as finbert_available

        result = search_headlines(query=symbol, limit=8)
        if result.get("status") != "ok" or not result.get("items"):
            return None
        titles = [i["title"] for i in result["items"]]
        sentiment_label = None
        if finbert_available():
            sentiment_result = analyze_batch(titles)
            if sentiment_result.get("available"):
                scores = [r["score"] for r in sentiment_result["results"]]
                avg = sum(scores) / len(scores) if scores else None
                sentiment_label = ("Positive" if avg >= 70 else "Negative" if avg < 40 else "Neutral") if avg is not None else None
        return {"headlines": titles[:5], "sentiment_label": sentiment_label}
    except Exception as e:
        logger.info("research_agency_service: news_analyst failed for %s: %s", symbol, e)
        return None


def _gather_macro(symbol: str) -> Optional[Dict]:
    try:
        from services.world_engine_service import get_region_snapshot
        region = _guess_region(symbol)
        snapshot = get_region_snapshot(region, news_limit=3, include_sentiment=False)
        if not snapshot.get("available"):
            return None
        macro = snapshot.get("macro") or {}
        if not macro.get("available"):
            return {"region": region, "region_label": snapshot.get("label"), "indicators": None}
        return {
            "region": region,
            "region_label": snapshot.get("label"),
            "macro_source": snapshot.get("macro_source"),
            "indicators": macro.get("indicators"),
        }
    except Exception as e:
        logger.info("research_agency_service: macro_analyst failed for %s: %s", symbol, e)
        return None


def _gather_fundamentals(symbol: str) -> Optional[Dict]:
    try:
        from services.fundamentals_service import get_fundamentals
        result = get_fundamentals(symbol)
        if not result.get("available"):
            return None
        return {
            "eps": result.get("eps"),
            "revenue": result.get("revenue"),
            "pe_ratio": result.get("pe_ratio"),
        }
    except Exception as e:
        logger.info("research_agency_service: fundamentals_analyst failed for %s: %s", symbol, e)
        return None


def _gather_all(symbol: str) -> Dict:
    """Stage 1: run every data-gathering agent. Each is independent and
    failure-isolated -- one angle coming back empty never blocks the
    others, same graceful-degradation convention as every service this
    module calls into."""
    return {
        "technical": _gather_technical(symbol),
        "news_sentiment": _gather_news_sentiment(symbol),
        "macro": _gather_macro(symbol),
        "fundamentals": _gather_fundamentals(symbol),
    }


def _render_summary(symbol: str, gathered: Dict) -> str:
    """Turns Stage 1's real data into the plain-text brief every Stage-2
    debate agent argues from. Any angle that came back None is rendered
    as an explicit "暫無" line, not silently omitted -- an omitted line
    invites a debate agent to fill the gap with a guess; an explicit
    "no data" line does not."""
    lines = [f"股票代號：{symbol}"]

    tech = gathered.get("technical")
    if tech:
        lines.append(
            f"技術面：Confluence方向 {tech.get('direction', '未知')}"
            f"（信心度 {tech.get('confidence_pct', '-')}%），"
            f"市場regime：{tech.get('regime', '未知')}"
        )
        if tech.get("bullish_signals"):
            lines.append(f"利好訊號：{'; '.join(tech['bullish_signals'])}")
        if tech.get("bearish_signals"):
            lines.append(f"利淡訊號：{'; '.join(tech['bearish_signals'])}")
    else:
        lines.append("技術面：暫無數據")

    news = gathered.get("news_sentiment")
    if news:
        lines.append(f"新聞情緒：{news.get('sentiment_label') or '暫無情緒分析'}")
        if news.get("headlines"):
            lines.append("近期頭條：" + "；".join(news["headlines"][:3]))
    else:
        lines.append("新聞面：暫無數據")

    macro = gathered.get("macro")
    if macro and macro.get("indicators"):
        ind = macro["indicators"]
        macro_bits = [f"{k}={v['value']}（{v['date']}）" for k, v in ind.items() if v]
        lines.append(f"宏觀（{macro.get('region_label', macro.get('region'))}）：{'、'.join(macro_bits) if macro_bits else '暫無'}")
    else:
        lines.append("宏觀面：暫無數據")

    fund = gathered.get("fundamentals")
    if fund:
        eps = fund.get("eps") or {}
        rev = fund.get("revenue") or {}
        lines.append(
            f"基本面：EPS {eps.get('value', '暫無')}，"
            f"營收 {rev.get('value', '暫無')}（{rev.get('fiscal_year', '-')}年度），"
            f"P/E {fund.get('pe_ratio', '暫無')}"
        )
    else:
        lines.append("基本面：暫無數據（可能非美股SEC申報公司）")

    return "\n".join(lines)


_PERSONA_PROMPTS = {
    "bull": "你係一個睇好嘅股票分析員（Bull）。淨係用返下面提供嘅真實多角度數據（技術面/新聞面/宏觀面/基本面），用2-3句講你點解睇好，如果某個角度標明「暫無數據」就唔好評論嗰個角度，唔好捏造數字。",
    "bear": "你係一個睇淡嘅股票分析員（Bear）。淨係用返下面提供嘅真實多角度數據（技術面/新聞面/宏觀面/基本面），用2-3句講你點解睇淡，如果某個角度標明「暫無數據」就唔好評論嗰個角度，唔好捏造數字。",
    "risk_manager": "你係一個風控經理（Risk Manager）。淨係用返下面提供嘅真實多角度數據，用2-3句指出最大嘅風險係咩（可以包括宏觀/基本面風險，唔淨係技術面），如果某個角度標明「暫無數據」就唔好評論嗰個角度，唔好捏造數字。",
}


def run_research(symbol: str, lang: str = None) -> Dict:
    """
    The Research Agency's top-level entrypoint. Self-sufficient: gathers
    its own multi-angle data (Stage 1), unlike agent_debate_service.
    run_debate() which requires the caller to already have a context
    dict built.

    Returns:
        {"available": False, "message": "..."} -- DEEPINFRA_API_KEY not set
        {"available": True, "gathered": {...}, "summary": "...",
         "arguments": {"bull":..., "bear":..., "risk_manager":...},
         "verdict": "...", "disclaimer": "...", "error": None}
        {"available": True, "gathered": {...}, "error": "..."} -- a debate
            call itself failed (Stage 1 gathering never raises -- see
            _gather_all()'s per-agent try/except).
    """
    is_zh_default = not lang or lang in ("zh-HK", "zh-TW", "zh-CN")
    if not is_available():
        return {
            "available": False,
            "message": (
                "多角度研究功能需要設定 DEEPINFRA_API_KEY 先可以使用，暫時未開放。"
                if is_zh_default
                else "The Research Agency feature is not yet enabled."
            ),
        }

    symbol = (symbol or "").strip().upper()
    if not symbol:
        return {"available": False, "message": "請提供股票代號。" if is_zh_default else "A ticker symbol is required."}

    gathered = _gather_all(symbol)
    summary = _render_summary(symbol, gathered)

    lang_instruction = "" if is_zh_default else f" {ai_language_instruction(lang)}"
    arguments = {}
    total_tokens = 0

    try:
        for persona, instruction in _PERSONA_PROMPTS.items():
            prompt = f"{instruction}{lang_instruction}\n\n真實多角度數據：\n{summary}"
            arguments[persona] = get_ai_response(prompt, max_tokens=_MAX_TOKENS, provider=_PROVIDER).strip()
            total_tokens += ai_router.get_last_usage_tokens()

        arbiter_prompt = (
            "你係一個中立嘅仲裁者。下面有3個分析員嘅意見（Bull/Bear/Risk Manager），佢哋已經睇過"
            "技術面/新聞面/宏觀面/基本面嘅真實數據。睇完之後用3-4句總結邊一方論點比較有數據支持，"
            "並指出如果要跟，最需要留意嘅一點係咩。唔好加入你自己未提供嘅新數據，只可以評論返3個"
            f"分析員已經講嘅嘢。{lang_instruction}\n\n"
            f"Bull：{arguments['bull']}\n\n"
            f"Bear：{arguments['bear']}\n\n"
            f"Risk Manager：{arguments['risk_manager']}"
        )
        verdict = get_ai_response(arbiter_prompt, max_tokens=_MAX_TOKENS, provider=_PROVIDER).strip()
        total_tokens += ai_router.get_last_usage_tokens()
        ai_router.set_last_usage_tokens(total_tokens)

        return {
            "available": True,
            "gathered": gathered,
            "summary": summary,
            "arguments": arguments,
            "verdict": verdict,
            "disclaimer": (
                "以上由AI角色扮演生成，基於多角度真實數據綜合，僅供參考角度，並非投資建議。"
                if is_zh_default
                else "The above is AI role-play generated content synthesizing multiple real data angles, for reference only -- not investment advice."
            ),
            "error": None,
        }
    except Exception as e:
        ai_router.set_last_usage_tokens(total_tokens)
        logger.info("research_agency_service: research failed for %s: %s", symbol, e)
        return {"available": True, "gathered": gathered, "arguments": arguments or None, "verdict": None, "error": str(e)}
