
class AlphaEngine:
    @staticmethod
    def generate(features):
        score = (
            features["momentum"] * 0.5 +
            features["volume_pressure"] * 0.3 +
            features["volatility"] * 0.2
        )
        return {"alpha_score": score, "signal": "BUY" if score > 5 else "SELL" if score < 2 else "HOLD"}
