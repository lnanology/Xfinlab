
class StrategyAgent:
    @staticmethod
    def analyze(market_data):
        score = market_data.get("score", 50)
        if score > 70:
            return {"action": "BUY", "confidence": 0.8}
        elif score < 40:
            return {"action": "SELL", "confidence": 0.7}
        return {"action": "HOLD", "confidence": 0.5}
