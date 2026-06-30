"""Rule Engine Module - Evaluates trading rules and assigns scores"""

from typing import Dict


class RuleEngine:
    """Evaluates market conditions against predefined trading rules"""

    def evaluate(self, data: Dict) -> Dict[str, float]:
        """
        Evaluate market data against trading rules

        Args:
            data (Dict): Market data containing volume_ratio, trend, breakout, sentiment

        Returns:
            Dict[str, float]: Rule evaluation results with scores
        """
        results = {}

        # Rule 1: Volume spike - volume_ratio > 2 scores +20
        if data.get("volume_ratio", 0) > 2:
            results["volume_spike"] = 20.0

        # Rule 2: Trend up - trend == "bullish" scores +30
        if data.get("trend", "").lower() == "bullish":
            results["trend_up"] = 30.0

        # Rule 3: Breakout - breakout == True scores +25
        if data.get("breakout", False):
            results["breakout"] = 25.0

        # Rule 4: Bullish sentiment - sentiment == "bullish" scores +25
        if data.get("sentiment", "").lower() == "bullish":
            results["bullish_sentiment"] = 25.0

        return results
