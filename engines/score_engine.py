"""Score Engine Module - Calculates overall strategy score"""

from typing import Dict


class ScoreEngine:
    """Aggregates rule evaluation scores into a total strategy score"""

    def calculate(self, rule_scores: Dict[str, float]) -> Dict[str, float]:
        """
        Calculate total strategy score from rule results

        Args:
            rule_scores (Dict[str, float]): Rule evaluation results from RuleEngine

        Returns:
            Dict[str, float]: Score summary with total and percentage
        """
        max_possible = 100.0  # Maximum possible score (20 + 30 + 25 + 25)

        total_score = sum(rule_scores.values())
        score_percent = (total_score / max_possible) * 100 if max_possible > 0 else 0.0

        return {"total_score": total_score, "score_percent": round(score_percent, 2)}
