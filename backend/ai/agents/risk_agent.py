
class RiskAgent:
    @staticmethod
    def analyze(volatility, event_risk, news_score):
        risk = volatility * 0.4 + event_risk * 0.3 + (100 - news_score) * 0.3
        return {"risk_score": risk, "level": "HIGH" if risk > 60 else "MEDIUM" if risk > 30 else "LOW"}
