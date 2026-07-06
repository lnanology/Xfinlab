
class AnalystAgent:
    @staticmethod
    def analyze(market_data):
        return {"trend": "UP" if market_data.get("price", 100) > 100 else "DOWN", "confidence": 0.7}
