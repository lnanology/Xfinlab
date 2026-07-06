
class MarketBrain:
    @staticmethod
    def think(stream_data, events, tensor):
        score = 50
        if "BREAKOUT" in events:
            score += 20
        if "DUMP" in events:
            score -= 30
        score += tensor["market_link"] * 10
        if score > 70:
            return "AGGRESSIVE_BUY"
        elif score < 40:
            return "SELL"
        return "HOLD"
