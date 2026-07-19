"""
XFINLAB News Engine
Analyzes news sentiment and generates news score

2026-07-19 Stage 2 roadmap upgrade ("FinBERT 新聞情緒升級"): sentiment used
to come purely from a hand-picked 15-word positive/negative keyword list
below -- "beat" and "cut" scored the same +/-5 regardless of context,
sarcasm, or negation ("shares FALL despite BEAT on earnings" would score
both ways and roughly cancel out). analyze() now tries
services/finbert_sentiment_service.py first (ProsusAI/finbert, a real
transformer model fine-tuned on financial text, called via the
HuggingFace Inference API) and only falls back to the keyword heuristic
below when FinBERT is unavailable (no HF_API_TOKEN configured, or the
API call fails) -- consistent with this codebase's standing rule of
degrading honestly rather than silently mixing methods. The returned
dict gained a "method" field ("finbert" | "keyword_heuristic") so
callers/logs can always tell which one actually produced a given score;
"score" and "sentiment" keep their original meaning/scale/thresholds so
every existing caller (api/ai_analysis.py, api/full_analysis_v3.py,
backend/core/pipeline.py, services/dashboard_snapshot_service.py,
growth/scheduler.py) needs no changes.
"""

from typing import List, Dict

from services.finbert_sentiment_service import analyze_batch as finbert_analyze_batch


class NewsEngine:
    """Analyzes news articles and calculates sentiment score"""

    # Positive/negative keyword lists -- only used as the fallback path
    # when FinBERT is unavailable (see module docstring).
    POSITIVE_WORDS = [
        "growth", "profit", "bullish", "strong", "record",
        "beat", "surge", "rally", "upgrade", "buy",
        "positive", "gain", "rise", "outperform", "exceed"
    ]
    NEGATIVE_WORDS = [
        "loss", "bearish", "weak", "decline", "miss",
        "fall", "drop", "downgrade", "sell", "negative",
        "risk", "concern", "warning", "cut", "below"
    ]

    @staticmethod
    def _score_to_sentiment(score: float) -> str:
        if score >= 70:
            return "Positive"
        elif score >= 40:
            return "Neutral"
        else:
            return "Negative"

    @staticmethod
    def _keyword_scores(texts: List[str]) -> List[float]:
        """The original rule-based scorer, kept as the honest fallback
        path for when FinBERT isn't configured/available."""
        scores = []
        for text in texts:
            text = text.lower()
            article_score = 50  # Neutral base
            for word in NewsEngine.POSITIVE_WORDS:
                if word in text:
                    article_score += 5
            for word in NewsEngine.NEGATIVE_WORDS:
                if word in text:
                    article_score -= 5
            scores.append(max(0, min(100, article_score)))
        return scores

    @staticmethod
    def analyze(news_data: List[Dict]) -> Dict:
        """
        Analyze news sentiment

        Args:
            news_data: List of news articles with title and summary

        Returns:
            Dict with score, sentiment, article_count, summary, and method
            ("finbert" | "keyword_heuristic" -- which scorer actually
            produced this result).
        """
        if not news_data:
            return {
                "score": 50,
                "sentiment": "Neutral",
                "article_count": 0,
                "summary": "No news available",
                "method": "none",
            }

        texts = [(article.get("title", "") + " " + article.get("summary", "")).strip() for article in news_data]

        finbert_result = finbert_analyze_batch(texts)
        if finbert_result.get("available"):
            per_article_scores = [r["score"] for r in finbert_result["results"]]
            method = "finbert"
        else:
            per_article_scores = NewsEngine._keyword_scores(texts)
            method = "keyword_heuristic"

        avg_score = round(sum(per_article_scores) / len(per_article_scores), 2)
        sentiment = NewsEngine._score_to_sentiment(avg_score)

        return {
            "score": avg_score,
            "sentiment": sentiment,
            "article_count": len(news_data),
            "summary": f"{sentiment} news sentiment based on {len(news_data)} articles",
            "method": method,
        }
