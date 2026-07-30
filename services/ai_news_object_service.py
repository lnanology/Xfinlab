"""
AI_NEWS_OBJECT Service -- Phase 1 of the AI Intelligence Engine (2026-07-31).

Builds ONE structured "AI_NEWS_OBJECT" per event cluster from
services/news_dedup_engine.py -- the schema from the user's "AI
Intelligence Engine" proposal, adapted to what this codebase can
HONESTLY compute today rather than inventing plausible-looking numbers
for pipeline stages that don't exist yet.

Fields NOT populated in Phase 1 (impact_score, confidence, probability,
risk_level, time_horizon, event_chain) are left explicitly None with
`quant_pending: True` on the object, rather than filled with an LLM's
made-up 0-100 "vibe" score. Phase 2 wires these to REAL, already-built
quant engines already in this codebase (RegimeDetector's Bayesian
posterior, backtest_service.py's historical win-rates,
market_structure_engine.py's disclosed composite scores) so every number
that eventually lands here is traceable to an actual computation -- the
same discipline chart_pattern_service.py's PATTERN_CONFIDENCE and
market_structure_engine.py's `weights_calibrated: False` disclosure
already hold this codebase to.

Data used to build each object is ONLY headline titles, source names,
links, and publish times from XFINLAB's own already-vetted news sources
(rss_news_service.py, gdelt_news_service.py, NewsService's NewsAPI feed)
-- never full article text (none of those sources store that -- see each
one's own minimal-retention convention). The AI-generated `summary` field
is explicitly prompted to extract only facts already present across
those titles, never to invent additional detail -- the "fact extraction,
not republishing" posture the user's own proposal called for to manage
copyright risk.
"""

import hashlib
import logging
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional

from ai.ai_router import get_ai_response
from services.finbert_sentiment_service import analyze_batch as finbert_analyze_batch

logger = logging.getLogger(__name__)

# v1 entity/ticker heuristic -- NOT a full named-entity-recognition
# model. Catches (a) cashtag-style mentions ($AAPL) and (b) a small,
# manually curated list of major companies/indices/central banks
# commonly covered in financial wires. Documented gap, not silently
# assumed complete: a headline about a company not in this list, and not
# written as "$TICKER", won't be tagged -- expand this list incrementally
# as real gaps are found, same convention as rss_news_service.py's own
# "explicitly ruled out this pass" sections.
_CASHTAG_RE = re.compile(r"\$([A-Z]{1,5})\b")
_KNOWN_ENTITIES = {
    "apple": "AAPL", "microsoft": "MSFT", "nvidia": "NVDA", "amazon": "AMZN",
    "google": "GOOGL", "alphabet": "GOOGL", "meta": "META", "tesla": "TSLA",
    "netflix": "NFLX", "amd": "AMD", "intel": "INTC", "broadcom": "AVGO",
    "tsmc": "TSM", "samsung": "005930.KS", "berkshire": "BRK.B",
    "jpmorgan": "JPM", "goldman sachs": "GS", "boeing": "BA",
    "exxon": "XOM", "chevron": "CVX", "walmart": "WMT",
    "federal reserve": "FED", "the fed": "FED", "ecb": "ECB",
    "bank of japan": "BOJ", "bank of england": "BOE",
}

_SENTIMENT_LABEL_MAP = {"positive": "bullish", "negative": "bearish", "neutral": "neutral"}

_SUMMARY_PROMPT_TEMPLATE = """你係一個財經事實整理助手。以下係{n}個新聞來源就同一單新聞事件嘅標題（唔係全文，冇全文可用）：

{titles_block}

請淨係根據以上標題入面已經出現嘅資訊，用2-3句話（書面中文）整理呢單事件講緊乜嘢。
規則：
1. 唔可以加入標題以外冇出現過嘅具體數字、人名、細節（如果標題冇提及原因，就唔好臆測原因）。
2. 唔可以用「建議買入/沽出」或者任何投資建議字眼。
3. 如果唔同標題講法有出入，可以講「消息來源說法唔完全一致」，唔好自己判斷邊個啱。
4. 只需輸出整理後嘅事實描述，唔使加免責聲明段落。"""


def _extract_entities(titles: List[str]) -> List[str]:
    found = set()
    joined_lower = " ".join(titles).lower()
    for name, ticker in _KNOWN_ENTITIES.items():
        if name in joined_lower:
            found.add(ticker)
    for title in titles:
        for m in _CASHTAG_RE.findall(title):
            found.add(m)
    return sorted(found)


def _make_id(cluster: List[Dict]) -> str:
    links = sorted(item["link"] for item in cluster)
    digest = hashlib.sha256("|".join(links).encode("utf-8")).hexdigest()[:16]
    return f"news_{digest}"


def _importance_score(cluster: List[Dict]) -> float:
    """0-100 heuristic -- NOT backtested/calibrated (unlike
    market_structure_engine.py, there's no `weights_calibrated` flag here
    because there's no weight-fitting attempt at all yet, just a
    documented rule of thumb). More independent sources covering the same
    event scores higher; an official company-announcement/press-release
    source (rss_news_service.py's "company_announcement" kind) counts as
    a primary-source bonus over generic market-news wire coverage."""
    source_count = len(cluster)
    source_score = min(source_count / 5.0, 1.0) * 60  # caps once 5+ sources agree
    has_official = any(item.get("kind") == "company_announcement" for item in cluster)
    official_bonus = 40 if has_official else 0
    return round(min(source_score + official_bonus, 100), 1)


def _sentiment_and_contradiction(titles: List[str]) -> Dict:
    """Real FinBERT call when HF_API_TOKEN is configured; returns
    sentiment=None (never a fabricated 'neutral') when it isn't
    configured or the call fails -- same honesty contract
    finbert_sentiment_service.py already requires of its callers
    elsewhere in this codebase."""
    result = finbert_analyze_batch(titles)
    if not result.get("available"):
        return {
            "sentiment": None, "sentiment_confidence": None,
            "contradiction_score": None, "sentiment_source": None,
            "message": result.get("message"),
        }

    scores = [r["score"] for r in result["results"]]
    avg_score = sum(scores) / len(scores)
    overall_label = "positive" if avg_score >= 60 else "negative" if avg_score <= 40 else "neutral"

    # Contradiction: how much do individual sources disagree on
    # DIRECTION, not just distance from neutral -- e.g. 3 sources all
    # mildly positive = low contradiction; 2 clearly positive + 2 clearly
    # negative on the SAME event = high contradiction, a genuinely useful
    # signal ("sources disagree on whether this is good news").
    spread = (max(scores) - min(scores)) if len(scores) > 1 else 0.0

    return {
        "sentiment": _SENTIMENT_LABEL_MAP.get(overall_label, "neutral"),
        "sentiment_confidence": round(avg_score, 1),
        "contradiction_score": round(min(spread, 100), 1),
        "sentiment_source": "finbert",
    }


def _build_summary(cluster: List[Dict]) -> Optional[str]:
    """AI call wrapped in try/except -- same graceful-degradation
    convention as global_macro_commentary_service.py: on any failure,
    return None and let the caller ship the object without a summary
    rather than blocking or fabricating one."""
    titles = [item["title"] for item in cluster]
    titles_block = "\n".join(f"- {t}" for t in titles)
    prompt = _SUMMARY_PROMPT_TEMPLATE.format(n=len(titles), titles_block=titles_block)
    try:
        return get_ai_response(prompt, max_tokens=250).strip()
    except Exception as e:
        logger.info("ai_news_object_service: summary generation failed: %s", e)
        return None


def build_news_object(cluster: List[Dict], generate_ai_summary: bool = True) -> Dict:
    """
    Builds one AI_NEWS_OBJECT from a cluster of same-event headlines (see
    services/news_dedup_engine.cluster_headlines()).

    `generate_ai_summary=False` skips the AI call entirely (e.g. bulk
    backfill/testing where paying for one AI call per cluster isn't
    justified) -- `summary` is then None; every other field is still
    computed for real, nothing else is skipped.
    """
    if not cluster:
        raise ValueError("build_news_object() requires a non-empty cluster")

    titles = [item["title"] for item in cluster]
    citations = [
        {
            "title": item["title"],
            "link": item["link"],
            "source": item.get("source"),
            "published_at": item.get("published_at"),
        }
        for item in cluster
    ]

    sentiment_info = _sentiment_and_contradiction(titles)
    entities = _extract_entities(titles)

    return {
        "id": _make_id(cluster),
        "title": max(titles, key=len),  # longest title tends to carry the most detail among paraphrases of the same event
        "summary": _build_summary(cluster) if generate_ai_summary else None,
        "summary_is_ai_generated": generate_ai_summary,
        "entities": entities,
        "affected_assets": entities,
        "sector": None,   # Phase 2+ -- needs a real sector taxonomy lookup, not guessed
        "country": None,  # Phase 2+
        "market": None,   # Phase 2+
        "sentiment": sentiment_info["sentiment"],
        "sentiment_confidence": sentiment_info["sentiment_confidence"],
        "sentiment_source": sentiment_info["sentiment_source"],
        "contradiction_score": sentiment_info["contradiction_score"],
        "source_count": len(cluster),
        "importance": _importance_score(cluster),
        # ---- Phase 2 fields: deliberately None, never fabricated ----
        "impact_score": None,
        "confidence": None,
        "probability": None,
        "risk_level": None,
        "time_horizon": None,
        "event_chain": None,
        "quant_pending": True,
        "citations": citations,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


if __name__ == "__main__":
    import json
    sample_cluster = [
        {"title": "Apple shares jump 3% on AI chip demand", "link": "https://a.com/1", "source": "Investing.com", "published_at": "2026-07-30T10:00:00+00:00", "kind": "market_news"},
        {"title": "AI chip demand lifts Apple stock higher", "link": "https://b.com/1", "source": "GDELT", "published_at": "2026-07-30T10:30:00+00:00"},
    ]
    obj = build_news_object(sample_cluster, generate_ai_summary=False)
    print(json.dumps(obj, indent=2, ensure_ascii=False))
