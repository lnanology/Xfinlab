"""
AI Journalist Service -- Phase 3 of the AI Intelligence Engine (2026-07-31).

Takes an AI_NEWS_OBJECT that has already been through:
  1. services/ai_news_object_service.build_news_object() (Phase 1 --
     summary/entities/sentiment/importance/citations, real data only)
  2. services/news_impact_engine.enrich_with_quant_signals() (Phase 2 --
     confidence/probability/risk_level/time_horizon from real
     market_structure_engine + historical_analog_service reads, or left
     None/quant_pending if no ticker resolved)

...and narrates it into one human-readable paragraph via
ai/ai_router.get_ai_response() -- the "AI Journalist" layer from the
user's original proposal. This stage adds NO new facts or numbers of its
own: it only puts existing, already-computed fields into readable
sentences. If Phase 2 hasn't resolved (quant_pending still True), the
narrative says so plainly rather than inventing a confidence/probability
reading to sound complete.

Compliance posture (same rule as ai_news_object_service.py's
_SUMMARY_PROMPT_TEMPLATE rule 2, reused verbatim in the prompt below by
deliberate duplication -- not imported, so this module doesn't quietly
break if that other module's prompt wording ever changes for unrelated
reasons; keep both in sync manually if the rule itself changes):
  - never uses "buy/sell" or other recommendation language
  - explicitly labels the output as AI-generated (narrative_is_ai_generated)
  - states plainly when quant data is unavailable, never fills the gap
    with invented certainty

Graceful degradation: any AI-call failure returns narrative=None (same
try/except contract as ai_news_object_service._build_summary() and
global_macro_commentary_service.get_region_commentary()) -- callers must
handle a missing narrative, never treat None as "neutral" text.
"""

import logging
from typing import Dict, Optional

from ai.ai_router import get_ai_response

logger = logging.getLogger(__name__)

_LANG_INSTRUCTION = {
    "zh-HK": "用香港粵語書面語回覆，簡潔直接，好似記者出快訊咁。",
    "zh-TW": "用台灣繁體中文回覆，簡潔直接，像記者發快訊一樣。",
    "zh-CN": "用简体中文回复，简洁直接，像记者发快讯一样。",
    "en": "Reply in English, concise and direct, like a wire-service news brief.",
}

_NARRATIVE_RULES = """規則：
1. 只可以用下面提供嘅資料，唔可以加入冇出現過嘅數字、人名或者原因。
2. 唔可以用「建議買入/沽出」或者任何投資建議字眼，呢個係新聞式敘述，唔係操作建議。
3. 如果「量化訊號」話明未有數據（quant pending），要喺文中直接講「呢單新聞暫時未有配對嘅量化技術面數據」，唔好扮有數據或者自己估一個。
4. 如果唔同消息來源講法有出入（contradiction_score偏高），要喺文中提一句。
5. 只需輸出敘述本身，唔使加標題或者免責聲明段落。"""


def _format_quant_block(news_object: Dict) -> str:
    """Renders ONLY the Phase-2 fields that actually resolved (quant_pending
    False) into prompt-ready lines -- never invents a placeholder line for
    a field that's still None."""
    if news_object.get("quant_pending", True):
        note = news_object.get("quant_signals", {}).get("note")
        return f"（量化技術面數據暫時未有配對：{note}）" if note else "（量化技術面數據暫時未有配對）"

    lines = []
    if news_object.get("confidence") is not None:
        lines.append(f"現時技術結構信心分數：{news_object['confidence']}/100")
    if news_object.get("probability") is not None:
        lines.append(f"歷史類比勝率：{news_object['probability']}%")
    if news_object.get("impact_score") is not None:
        lines.append(f"歷史波動幅度推算嘅Impact Score：{news_object['impact_score']}/100")
    if news_object.get("risk_level") is not None:
        lines.append(f"風險水平（based on 現時波動）：{news_object['risk_level']}")
    if news_object.get("time_horizon") is not None:
        lines.append(f"對應時間範圍：{news_object['time_horizon']}")
    assets_used = news_object.get("quant_signals", {}).get("assets_used") or []
    if assets_used:
        lines.append(f"以上數字嚟自：{', '.join(assets_used)} 嘅現時技術結構＋歷史回測統計，並非對呢單新聞本身嘅預測")
    return "\n".join(f"- {l}" for l in lines) if lines else "（量化技術面數據暫時未有配對）"


def _build_prompt(news_object: Dict, lang: str) -> str:
    summary = news_object.get("summary") or "（暫時未有AI事實摘要）"
    entities = news_object.get("affected_assets") or []
    entities_line = "、".join(entities) if entities else "（未有辨識到具體資產）"
    sentiment = news_object.get("sentiment")
    sentiment_conf = news_object.get("sentiment_confidence")
    sentiment_line = (
        f"{sentiment}（信心 {sentiment_conf}/100，FinBERT）" if sentiment else "（暫時未有情緒分析數據）"
    )
    contradiction = news_object.get("contradiction_score")
    contradiction_line = (
        f"消息來源分歧程度：{contradiction}/100（分數越高代表來源講法越唔一致）"
        if contradiction is not None else "（未有計算來源分歧程度）"
    )
    source_count = news_object.get("source_count", 0)
    quant_block = _format_quant_block(news_object)
    lang_instruction = _LANG_INSTRUCTION.get(lang, _LANG_INSTRUCTION["zh-HK"])

    return f"""你係一個財經新聞記者，負責將以下結構化資料寫成一段3-5句嘅新聞式敘述：

事實摘要：{summary}
涉及資產：{entities_line}
新聞來源數目：{source_count}
情緒分析：{sentiment_line}
{contradiction_line}

量化技術面：
{quant_block}

{lang_instruction}

{_NARRATIVE_RULES}"""


def add_narrative(news_object: Dict, lang: str = "zh-HK", max_tokens: int = 400) -> Dict:
    """
    Mutates and returns `news_object`, adding:
      - "narrative": the AI-generated news-brief paragraph, or None if the
        AI call failed
      - "narrative_is_ai_generated": True (always set, even when narrative
        is None, so callers can distinguish "we tried and it's labeled AI"
        from a field that was never touched by this pipeline stage)
      - "narrative_lang": the language the narrative was generated in

    Never raises -- any AI-router failure degrades to narrative=None,
    same contract as every other AI-call site in this codebase.
    """
    prompt = _build_prompt(news_object, lang)
    try:
        narrative = get_ai_response(prompt, max_tokens=max_tokens).strip()
    except Exception as e:
        logger.info("ai_journalist_service: narrative generation failed: %s", e)
        narrative = None

    news_object["narrative"] = narrative
    news_object["narrative_is_ai_generated"] = True
    news_object["narrative_lang"] = lang
    return news_object


if __name__ == "__main__":
    import json

    sample = {
        "id": "news_test",
        "summary": "多個消息來源報道蘋果股價因AI晶片需求上升而上漲。",
        "affected_assets": ["AAPL"],
        "source_count": 2,
        "sentiment": "bullish",
        "sentiment_confidence": 78.0,
        "contradiction_score": 5.0,
        "quant_pending": False,
        "confidence": 65.5,
        "probability": 61.9,
        "impact_score": 46.0,
        "risk_level": "medium",
        "time_horizon": "medium_term",
        "quant_signals": {"assets_used": ["AAPL"]},
    }
    result = add_narrative(dict(sample))
    print(json.dumps(result, indent=2, ensure_ascii=False))
