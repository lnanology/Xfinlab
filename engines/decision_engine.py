"""Decision Engine Module - Makes final trading decision based on score"""

from typing import Dict


class DecisionEngine:
    """Makes final trading decisions based on strategy score"""

    def decide(self, score_result: Dict[str, float]) -> Dict[str, str]:
        """
        Make trading decision based on total score

        Args:
            score_result (Dict[str, float]): Score result from ScoreEngine

        Returns:
            Dict[str, str]: Trading decision
        """
        total_score = score_result.get("total_score", 0)

        if total_score >= 80:
            decision = "Strong Buy"
        elif total_score >= 60:
            decision = "Bullish"
        elif total_score >= 40:
            decision = "Neutral"
        else:
            decision = "Bearish"

        return {"total_score": total_score, "decision": decision}
