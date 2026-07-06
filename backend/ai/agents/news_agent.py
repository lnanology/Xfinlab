
class NewsAgent:
    @staticmethod
    def analyze(news_data):
        if not news_data:
            return {"score": 50, "sentiment": "neutral"}
        positive = negative = 0
        for n in news_data:
            text = (n.get("title","") + " " + n.get("summary","")).lower()
            if any(w in text for w in ["growth","profit","surge","beat","up","rise"]):
                positive += 1
            if any(w in text for w in ["loss","drop","lawsuit","risk","fall","down"]):
                negative += 1
        score = max(0, min(100, 50 + (positive - negative) * 10))
        return {"score": score, "sentiment": "bullish" if score > 60 else "bearish" if score < 40 else "neutral"}
