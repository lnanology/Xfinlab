
class RegimeDetector:
    @staticmethod
    def detect(market_data):
        volatility = market_data.get("volatility", 50)
        if volatility > 70:
            return "HIGH_VOLATILITY"
        elif volatility < 30:
            return "LOW_VOLATILITY"
        return "NORMAL"
