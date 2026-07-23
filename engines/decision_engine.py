"""Decision Engine Module

2026-07-23 note (platform audit finding): despite the name, this class was
NOT actually where XFINLAB's real investment decisions get synthesized.
Three separate, independent scoring/rating pipelines exist in this codebase
today:

  1. api/analysis_api.py -- RuleEngine -> ScoreEngine -> RiskEngine ->
     DecisionEngine.decide() (this class's original method, kept below
     unchanged). This router is NEVER mounted in backend/main.py -- it is
     dead code, unreachable from any live URL. Only tests/test_suite.py and
     the root-level test_decision.py manual script exercise it.
  2. api/full_analysis_v3.py -- the real, live `/api/full-analysis/{ticker}`
     endpoint -- computes its own weighted final_score/rating via
     engines/scoring_engine.py's ScoringEngine.calculate(), bypassing this
     class entirely.
  3. api/ai_analysis.py -- the real, live ai-analysis.html pipeline (the
     most-visited analysis page) -- derives its own bull/bear/flat split
     and a third, separate BUY/SELL/HOLD "hero_rating" via inline
     thresholds, also bypassing both this class and ScoringEngine.

decide_full() below is the first step in un-forking this: it exposes
ScoringEngine's real weighted formula through this class so future callers
have one actual "decision engine" to call. full_analysis_v3.py has been
switched to call it (output is byte-for-byte identical to before -- it's
the same formula, just centralized). api/ai_analysis.py's separate
hero_rating logic has NOT been touched yet: unifying it would change the
BUY/SELL/HOLD label real users see today on the most-used page, which is a
product decision, not a pure refactor -- flagged for the user rather than
changed silently. api/analysis_api.py stays unmounted/dead as-is (not
deleted, per this repo's convention of not removing files without asking).
"""

from typing import Dict


class DecisionEngine:
    """Makes final trading decisions based on strategy score"""

    def decide(self, score_result: Dict[str, float]) -> Dict[str, str]:
        """
        Original 4-tier decision mapper. Kept exactly as-is: still used by
        api/analysis_api.py (dead/unmounted) and tests/test_suite.py's
        TestDecisionEngine, which asserts these exact thresholds.

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

    def decide_full(
        self,
        market_score: float,
        news_score: float,
        strategy_score: float,
        overall_risk: float
    ) -> Dict:
        """
        Real weighted synthesis (market/news/strategy scores minus a risk
        penalty -> 5-tier Strong Buy/Buy/Neutral/Sell/Strong Sell rating).
        Delegates to engines/scoring_engine.py's ScoringEngine so there is
        exactly one implementation of this formula; this is just the
        canonical place callers should reach for it going forward.
        """
        from engines.scoring_engine import ScoringEngine
        return ScoringEngine.calculate(
            market_score=market_score,
            news_score=news_score,
            strategy_score=strategy_score,
            overall_risk=overall_risk,
        )
