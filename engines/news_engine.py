"""
XFINLAB News Engine
Analyzes news sentiment and generates news score
"""

from typing import List, Dict


class NewsEngine:
    """Analyzes news articles and calculates sentiment score"""

    @staticmethod
    def analyze(news_data: List[Dict]) -> Dict:
        """
        Analyze news sentiment

        Args:
            news_data: List of news articles with title and summary

        Returns:
            Dict with score, sentiment, and summary
        """
        if not news_data:
            return {
                "score": 50,
                "sentiment": "Neutral",
                "article_count": 0,
                "summary": "No news available"
            }

        # Positive keywords
        positive_words = [
            "growth", "profit", "bullish", "strong", "record",
            "beat", "surge", "rally", "upgrade", "buy",
            "positive", "gain", "rise", "outperform", "exceed"
        ]

        # Negative keywords
        negative_words = [
            "loss", "bearish", "weak", "decline", "miss",
            "fall", "drop", "downgrade", "sell", "negative",
            "risk", "concern", "warning", "cut", "below"
        ]

        total_score = 0

        for article in news_data:
            text = (article.get("title", "") + " " + article.get("summary", "")).lower()
            article_score = 50  # Neutral base

            for word in positive_words:
                if word in text:
                    article_score += 5

            for word in negative_words:
                if word in text:
                    article_score -= 5

            # Cap between 0-100
            article_score = max(0, min(100, article_score))
            total_score += article_score

        avg_score = round(total_score / len(news_data), 2)

        if avg_score >= 70:
            sentiment = "Positive"
        elif avg_score >= 40:
            sentiment = "Neutral"
        else:
            sentiment = "Negative"

        return {
            "score": avg_score,
            "sentiment": sentiment,
            "article_count": len(news_data),
            "summary": f"{sentiment} news sentiment based on {len(news_data)} articles"
        }
