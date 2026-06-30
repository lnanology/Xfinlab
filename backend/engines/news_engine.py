class NewsEngine:
    POSITIVE_WORDS = [
        "beat",
        "growth",
        "surge",
        "strong",
        "record",
        "profit",
        "upgrade",
        "bullish",
        "expansion",
        "innovation"
    ]

    NEGATIVE_WORDS = [
        "miss",
        "drop",
        "decline",
        "loss",
        "downgrade",
        "bearish",
        "lawsuit",
        "investigation",
        "recession",
        "bankruptcy"
    ]

    @classmethod
    def analyze(cls, news_list):

        score = 50

        for article in news_list:

            text = (
                str(article.get("title", ""))
                + " "
                + str(article.get("summary", ""))
            ).lower()

            for word in cls.POSITIVE_WORDS:
                if word in text:
                    score += 5

            for word in cls.NEGATIVE_WORDS:
                if word in text:
                    score -= 5

        score = max(0, min(score, 100))

        if score >= 65:
            sentiment = "Positive"
        elif score <= 35:
            sentiment = "Negative"
        else:
            sentiment = "Neutral"

        impact = min(100, abs(score - 50) * 2)

        return {
            "sentiment": sentiment,
            "score": score,
            "impact": impact
        }