"""
FinBERT Sentiment Service -- Stage 2 roadmap item 2 (2026-07-19):
"FinBERT 新聞情緒升級" (FinBERT news sentiment upgrade).

Replaces the platform's old rule-based sentiment scoring (a hand-picked
15-word positive/negative keyword list in engines/news_engine.py -- see
that file's history) with ProsusAI/finbert, an open-source transformer
model fine-tuned specifically on financial text, via the HuggingFace
Inference API.

Why the Inference API instead of self-hosting the model:
  - This backend runs as a single small Railway dyno (see Procfile --
    plain `uvicorn backend.main:app`, no worker pool) with SQLite+
    Litestream. Loading a ~440MB PyTorch model in-process would add
    real memory pressure and cold-start latency to every deploy/restart
    on that tier.
  - No `transformers`/`torch` dependency exists in requirements.txt today
    -- adding them is a much bigger footprint than a `requests` call.
  - This codebase already has an established, working pattern for this
    exact tradeoff: ai/ai_router.py's DeepSeek/Groq/Claude calls are all
    plain HTTP requests to a hosted inference endpoint, gated behind an
    env-var API key check (see services/agent_debate_service.py's
    is_available()). This module follows the same shape.

Honesty contract (same standard as the rest of this codebase):
  - Gated entirely behind HF_API_TOKEN being configured. If it isn't
    set, analyze() returns {"available": False, ...} -- callers must
    fall back to their own labelled heuristic (e.g. the keyword engine),
    NEVER silently substitute a fabricated FinBERT-labelled score.
  - HuggingFace's hosted Inference API can return a 503 while a model is
    "cold" (spinning up) -- this is treated as a real failure state
    (available: False for that call), not retried into a fake success.
  - Every returned result carries "source": "finbert" so nothing
    downstream can accidentally attribute a keyword-heuristic score to
    FinBERT or vice versa.
"""

import logging
import os
from typing import Dict, List, Optional

from services.outbound_http import post_with_backoff

logger = logging.getLogger(__name__)

HF_API_TOKEN_ENV = "HF_API_TOKEN"
MODEL_ID = "ProsusAI/finbert"
INFERENCE_URL = f"https://api-inference.huggingface.co/models/{MODEL_ID}"

# FinBERT's 3 output labels, normalized to a 0-100 "bullishness" score the
# same way engines/news_engine.py's old keyword score worked (50 =
# neutral), so downstream consumers don't need to know which method
# produced the number.
_LABEL_TO_SCORE_ANCHOR = {"positive": 100, "neutral": 50, "negative": 0}


def is_available() -> bool:
    """HF_API_TOKEN must be configured -- see this module's docstring for
    why this is gated rather than silently falling back to a fabricated
    result."""
    return bool(os.getenv(HF_API_TOKEN_ENV))


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {os.getenv(HF_API_TOKEN_ENV)}",
        "Content-Type": "application/json",
    }


def _to_result(label_scores: List[Dict]) -> Dict:
    """label_scores: HF's per-label output for one input, e.g.
    [{"label": "positive", "score": 0.82}, {"label": "neutral", "score": 0.13}, ...]
    Returns a 0-100 score (weighted blend of all 3 label probabilities
    against their anchors, not just the top label) plus the top label."""
    by_label = {r["label"].lower(): r["score"] for r in label_scores}
    top_label = max(by_label, key=by_label.get)
    blended = sum(_LABEL_TO_SCORE_ANCHOR.get(lbl, 50) * prob for lbl, prob in by_label.items())
    return {
        "label": top_label,
        "confidence_pct": round(by_label[top_label] * 100, 1),
        "score": round(blended, 1),
    }


def analyze_batch(texts: List[str], timeout: float = 15) -> Dict:
    """
    texts: list of raw strings (headlines, post titles, etc -- truncated
    to FinBERT's ~512 token limit is the caller's responsibility for very
    long inputs, though headlines/titles are short enough in practice
    that this hasn't needed enforcing).

    Returns:
        {"available": True, "source": "finbert",
         "results": [{"label": "positive", "confidence_pct": 82.0, "score": 91.4}, ...]}
            -- one result per input text, same order
        {"available": False, "message": "..."} -- no token configured,
            or the API call failed/errored/returned a cold-model 503.
            Callers MUST fall back to their own labelled heuristic in
            this case, not treat this as "neutral".
    """
    if not texts:
        return {"available": False, "message": "冇文字可以分析"}
    if not is_available():
        return {"available": False, "message": f"未設定 {HF_API_TOKEN_ENV}，FinBERT情緒分析暫時未開放。"}

    try:
        response = post_with_backoff(
            INFERENCE_URL,
            json={"inputs": texts, "options": {"wait_for_model": True}},
            headers=_headers(),
            timeout=timeout,
        )
    except Exception as e:
        logger.info("finbert_sentiment_service: request failed: %s", e)
        return {"available": False, "message": f"FinBERT請求失敗：{e}"}

    if response.status_code != 200:
        logger.info("finbert_sentiment_service: HTTP %s: %s", response.status_code, response.text[:200])
        return {"available": False, "message": f"FinBERT暫時未能回應（HTTP {response.status_code}）"}

    try:
        payload = response.json()
        # Single-input calls sometimes come back as one flat list instead
        # of a list-of-lists -- normalize so the batch path is uniform.
        if payload and isinstance(payload[0], dict):
            payload = [payload]
        results = [_to_result(item) for item in payload]
    except Exception as e:
        logger.info("finbert_sentiment_service: unexpected response shape: %s", e)
        return {"available": False, "message": "FinBERT回應格式異常"}

    return {"available": True, "source": "finbert", "results": results}


def analyze_one(text: str, timeout: float = 15) -> Optional[Dict]:
    """Single-text convenience wrapper. Returns the per-text result dict
    (label/confidence_pct/score) or None if unavailable -- callers must
    handle None as "fall back to the keyword heuristic", never as
    "neutral"."""
    result = analyze_batch([text], timeout=timeout)
    if not result.get("available"):
        return None
    return result["results"][0]
