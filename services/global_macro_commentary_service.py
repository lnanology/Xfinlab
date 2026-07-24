"""
Global Macro + News AI Commentary (2026-07-24) -- the feature the user
asked for directly: "全球新聞+宏觀AI評語" (global news + macro AI commentary).

Combines, for one region:
  1. services/macro_data_service.get_macro_snapshot() -- World Bank
     macro indicators (GDP growth / inflation / unemployment), or an
     honest "unavailable" for Taiwan.
  2. services/global_news_region_service.get_region_headlines() --
     keyword-filtered headlines from the existing compliant RSS pool.
  3. services/finbert_sentiment_service.analyze_batch() -- real sentiment
     scoring on those headlines (falls back to NewsEngine's keyword
     heuristic the same way engines/news_engine.py already does, so this
     module never needs its own duplicate fallback logic).
  4. ai/ai_router.get_ai_response() -- a short (3-5 sentence) commentary
     paragraph synthesizing 1-3, in the caller's requested language.

This is explicitly NOT a real-time trading signal and never presents
itself as one -- the AI prompt below enforces stating outright that macro
figures are lagging annual data and headlines are general-wire coverage,
not a licensed per-market feed. This is the same "analysis/derived output,
not raw data redistribution" pattern already used everywhere else in this
codebase (see services/license_registry.py's design rationale) applied to
a brand-new asset: countries the platform has no licensed equity feed for
yet.
"""

import logging
from typing import Dict

from ai.ai_router import get_ai_response
from services.finbert_sentiment_service import analyze_batch as finbert_analyze_batch
from services.global_news_region_service import get_region_headlines
from services.macro_data_service import REGIONS, get_macro_snapshot

logger = logging.getLogger(__name__)


def _format_indicators_for_prompt(macro: Dict) -> str:
    if not macro.get("available"):
        return "（呢個地區暫時冇公開宏觀數據）"
    lines = []
    ind = macro["indicators"]
    if ind.get("gdp_growth_pct"):
        lines.append(f"GDP增長 {ind['gdp_growth_pct']['value']}%（{ind['gdp_growth_pct']['year']}年數據）")
    if ind.get("inflation_pct"):
        lines.append(f"通脹率 {ind['inflation_pct']['value']}%（{ind['inflation_pct']['year']}年數據）")
    if ind.get("unemployment_pct"):
        lines.append(f"失業率 {ind['unemployment_pct']['value']}%（{ind['unemployment_pct']['year']}年數據）")
    return "、".join(lines) if lines else "（呢個地區暫時冇公開宏觀數據）"


def get_region_commentary(region: str, lang: str = "zh-HK") -> Dict:
    """
    Returns:
        {"available": True, "region": "hk", "label": "香港",
         "macro": {...}, "news": {...}, "sentiment": {...} | None,
         "ai_commentary": "AI-generated paragraph"}
        {"available": False, "message": "..."} -- unknown region key only;
            every other failure mode (no macro data, no matching news, no
            FinBERT token configured) degrades gracefully into the
            response rather than erroring out, since a region-level
            summary should still render with whatever pieces succeeded.
    """
    cfg = REGIONS.get(region)
    if not cfg:
        return {"available": False, "message": f"未知地區代碼：{region}"}

    macro = get_macro_snapshot(region)
    news = get_region_headlines(region, limit=6)

    sentiment = None
    if news.get("items"):
        titles = [item["title"] for item in news["items"]]
        finbert_result = finbert_analyze_batch(titles)
        if finbert_result.get("available"):
            scores = [r["score"] for r in finbert_result["results"]]
            avg = round(sum(scores) / len(scores), 1)
            sentiment = {"available": True, "source": "finbert", "avg_score": avg,
                         "label": "Positive" if avg >= 70 else "Negative" if avg < 40 else "Neutral"}
        else:
            sentiment = {"available": False, "message": finbert_result.get("message")}

    headline_lines = "\n".join(f"- {item['title']}" for item in news.get("items", [])[:6]) or "（暫時冇相關頭條）"
    macro_line = _format_indicators_for_prompt(macro)
    sentiment_line = (
        f"新聞情緒評分 {sentiment['avg_score']}/100（{sentiment['label']}）"
        if sentiment and sentiment.get("available")
        else "（暫時未有情緒分析數據）"
    )

    lang_instruction = {
        "zh-HK": "用香港粵語書面語回覆，簡潔直接。",
        "zh-TW": "用台灣繁體中文回覆，簡潔直接。",
        "zh-CN": "用简体中文回复，简洁直接。",
        "en": "Reply in English, concise and direct.",
    }.get(lang, "用繁體中文回覆，簡潔直接。")

    prompt = f"""你係一個金融市場評論員。根據以下資料，為「{cfg['label']}」寫一段3-4句嘅市場概況評語：

宏觀數據：{macro_line}
{sentiment_line}
近期相關頭條：
{headline_lines}

要求：
1. {lang_instruction}
2. 如果宏觀數據話明係「暫時冇數據」，唔好扮有數據，直接講出嚟。
3. 唔好將呢段評語講成即市交易訊號，呢個只係背景概況，要在文中提及呢個係基於宏觀及新聞層面嘅概況，唔係即市股價分析。
4. 唔使加免責聲明段落，用返自然口語直接融入返兩句已經足夠。"""

    try:
        ai_commentary = get_ai_response(prompt, max_tokens=400)
    except Exception as e:
        logger.info("global_macro_commentary_service: AI call failed for region=%s: %s", region, e)
        ai_commentary = None

    return {
        "available": True,
        "region": region,
        "label": cfg["label"],
        "label_en": cfg["label_en"],
        "macro": macro,
        "news": news,
        "sentiment": sentiment,
        "ai_commentary": ai_commentary,
    }
