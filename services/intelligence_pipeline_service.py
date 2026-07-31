"""
Intelligence Pipeline Orchestrator -- Phase 4 of the AI Intelligence Engine
(2026-07-31).

Thin glue module wiring Phase 1-3 together into one call, so api/
intelligence.py's endpoints stay as thin as its existing /v1/events,
/v1/sentiment, /v1/debate routes (see that file's own docstring: it's a
"packaging layer", no business logic lives in the router itself).

Pipeline:
  raw headline items (rss_news_service.get_all_headlines()/search_headlines())
    -> services.news_dedup_engine.cluster_headlines()   (Phase 1: group same-event)
    -> services.ai_news_object_service.build_news_object()  (Phase 1: structured object)
    -> services.news_impact_engine.enrich_with_quant_signals()  (Phase 2: real quant fields)
    -> services.ai_journalist_service.add_narrative()   (Phase 3: readable narrative)
    -> services.event_chain_service.add_event_chain()   (Phase 5: non-causal cross-asset stats)

(Phase 4 is this module + api/intelligence.py's endpoints wrapping the
above -- there's no separate Phase 4 function to call.)

Cost/latency note: each cluster can trigger up to 2 AI calls (Phase 1
summary + Phase 3 narrative) plus real OHLC/market-structure/historical-
analog lookups per affected ticker (Phase 2) plus up to MAX_CHAIN_EDGES
more paired OHLC lookups (Phase 5). `max_clusters` bounds this per
request -- callers (api/intelligence.py) should keep it small and weight
the API-key quota accordingly (see services/intelligence_quota_service
.ENDPOINT_WEIGHT["intel"]), same cost-awareness already applied to the
debate endpoint (weight 5) for its 4 sequential LLM calls.
"""

import logging
from typing import Dict, List

from services.news_dedup_engine import cluster_headlines
from services.ai_news_object_service import build_news_object
from services.news_impact_engine import enrich_with_quant_signals
from services.ai_journalist_service import add_narrative
from services.event_chain_service import add_event_chain

logger = logging.getLogger(__name__)

_DEFAULT_MAX_CLUSTERS = 5


def build_intelligence_feed(
    items: List[Dict],
    max_clusters: int = _DEFAULT_MAX_CLUSTERS,
    lang: str = "zh-HK",
    generate_narrative: bool = True,
) -> List[Dict]:
    """
    Runs the full Phase 1-3 pipeline over raw headline items and returns a
    list of fully-built AI_NEWS_OBJECTs (newest-event-cluster first, same
    ordering cluster_headlines() already produces).

    `generate_narrative=False` skips both the Phase 1 AI summary and the
    Phase 3 AI narrative call (cheaper/faster path -- e.g. for a caller
    that only wants the real quant fields and citations, not prose).
    Every non-AI field (entities, sentiment, quant signals, citations)
    is still computed for real regardless of this flag.

    A failure enriching or narrating ANY single cluster is caught and
    logged, and that cluster still ships with whatever fields DID
    succeed (Phase 2/3's own internal try/except already guarantee this
    for the AI-call and per-ticker-lookup steps; this is a second,
    outer safety net so one cluster's unexpected exception can't take
    down the whole feed response)."""
    clusters = cluster_headlines(items)
    feed: List[Dict] = []
    for cluster in clusters[:max_clusters]:
        try:
            obj = build_news_object(cluster, generate_ai_summary=generate_narrative)
            obj = enrich_with_quant_signals(obj)
            obj = add_event_chain(obj)
            if generate_narrative:
                obj = add_narrative(obj, lang=lang)
            feed.append(obj)
        except Exception as e:
            logger.warning("intelligence_pipeline_service: cluster build failed, skipping: %s", e)
            continue
    return feed
