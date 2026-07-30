"""
News Dedup Engine -- Phase 1 of the AI Intelligence Engine (2026-07-31).

Per the user's "AI Intelligence Engine" proposal reviewed this session:
raw news has low resale value and copyright risk; ORIGINAL structured
analysis (built from real facts, clearly cited, never reproducing full
article text) is the differentiated, defensible product. This module is
the first pipeline stage: group near-duplicate headlines from XFINLAB's
existing news sources (rss_news_service.py's 4 wires, gdelt_news_service.py,
NewsService's NewsAPI feed) into "same underlying event, covered by N
sources" clusters -- the input services/ai_news_object_service.py needs
to build one structured AI_NEWS_OBJECT per real-world event instead of
one per article (which would just be re-publishing a wire's headline
list with extra steps).

Deliberately simple and deterministic (token-overlap + sequence-ratio
string similarity, no embedding model) for v1: cheap enough to run on
every ingestion cycle, easy to reason about and unit-test. A future
version could swap the similarity function for an embedding-based one
without changing cluster_headlines()'s signature or callers.
"""

import re
from datetime import datetime
from difflib import SequenceMatcher
from typing import Dict, List, Optional

_STOPWORDS = {
    "the", "a", "an", "to", "of", "in", "on", "for", "and", "with", "by",
    "is", "are", "at", "as", "its", "after", "says", "said", "will", "has",
    "have", "from", "amid", "over", "into", "new", "news",
}


def _normalize_title(title: str) -> str:
    """Lowercase, strip punctuation, drop stopwords -- for comparing
    titles across sources that word the SAME event differently (e.g.
    'Apple shares jump 3% on AI chip demand' vs 'AI chip demand lifts
    Apple stock')."""
    words = re.findall(r"[a-z0-9]+", title.lower())
    return " ".join(w for w in words if w not in _STOPWORDS)


def _title_similarity(a: str, b: str) -> float:
    """0..1 similarity via token-set (Jaccard) overlap blended with
    SequenceMatcher ratio. Jaccard alone misses reordered phrases;
    SequenceMatcher alone is too strict on paraphrases -- blending both
    catches more genuine same-event pairs without over-merging unrelated
    headlines that just happen to share common financial vocabulary
    ("stocks", "Fed", "shares")."""
    na, nb = _normalize_title(a), _normalize_title(b)
    if not na or not nb:
        return 0.0
    set_a, set_b = set(na.split()), set(nb.split())
    if not set_a or not set_b:
        return 0.0
    jaccard = len(set_a & set_b) / len(set_a | set_b)
    seq_ratio = SequenceMatcher(None, na, nb).ratio()
    return jaccard * 0.6 + seq_ratio * 0.4


def _parse_ts(item: Dict) -> Optional[datetime]:
    raw = item.get("published_at")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        return None


def cluster_headlines(
    items: List[Dict],
    similarity_threshold: float = 0.30,
    time_window_hours: float = 48,
) -> List[List[Dict]]:
    """
    Groups near-duplicate headlines (same underlying event, covered by
    multiple sources) into clusters. Each input item must have at least
    `title` and `link`; `published_at` (ISO-8601, may be missing/None)
    caps clustering to headlines published within `time_window_hours` of
    each other -- two unrelated stories that happen to share vocabulary
    ("Apple") months apart shouldn't merge just because their titles
    overlap.

    Each new item is compared only against each existing cluster's FIRST
    ("anchor") item -- O(n) per new item instead of O(cluster size), and
    the anchor is representative enough since every other member already
    matched it above threshold too.

    `similarity_threshold` default of 0.30 was picked empirically against
    this module's own __main__ smoke test: 3 genuinely-same-event
    paraphrased headlines scored 0.39-0.41 against each other, while
    every unrelated-headline pair scored 0.09-0.14 -- 0.30 sits with
    margin in the gap between those two clusters of scores rather than
    being guessed. Re-run `python services/news_dedup_engine.py` and
    re-check this margin if the similarity function itself ever changes.

    Returns clusters sorted newest-first by their most recent item's
    published_at (items with no parseable timestamp sort last).
    """
    clusters: List[List[Dict]] = []
    for item in items:
        if not item.get("title") or not item.get("link"):
            continue
        item_ts = _parse_ts(item)
        placed = False
        for cluster in clusters:
            anchor = cluster[0]
            if item.get("link") == anchor.get("link"):
                placed = True
                break
            sim = _title_similarity(item["title"], anchor["title"])
            if sim < similarity_threshold:
                continue
            anchor_ts = _parse_ts(anchor)
            if item_ts and anchor_ts:
                hours_apart = abs((item_ts - anchor_ts).total_seconds()) / 3600
                if hours_apart > time_window_hours:
                    continue
            cluster.append(item)
            placed = True
            break
        if not placed:
            clusters.append([item])

    def _cluster_sort_key(cluster: List[Dict]):
        timestamps = [_parse_ts(it) for it in cluster]
        real = [t for t in timestamps if t is not None]
        if not real:
            return (0, "")  # no real timestamp -- sorts before (older than) anything dated
        return (1, max(real).isoformat())

    clusters.sort(key=_cluster_sort_key, reverse=True)
    return clusters


if __name__ == "__main__":
    import json

    sample = [
        {"title": "Apple shares jump 3% on AI chip demand", "link": "https://a.com/1", "source": "A", "published_at": "2026-07-30T10:00:00+00:00"},
        {"title": "AI chip demand lifts Apple stock higher", "link": "https://b.com/1", "source": "B", "published_at": "2026-07-30T10:30:00+00:00"},
        {"title": "Fed holds interest rates steady", "link": "https://c.com/1", "source": "C", "published_at": "2026-07-30T09:00:00+00:00"},
        {"title": "Apple stock surges as AI chip orders climb", "link": "https://d.com/1", "source": "D", "published_at": "2026-07-30T11:00:00+00:00"},
    ]
    for cluster in cluster_headlines(sample):
        print(json.dumps(cluster, indent=2))
        print("---")
