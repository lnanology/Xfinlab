"""
XFINLAB Core Decision System V1
Test Script - Full Decision Pipeline
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engines.rule_engine import RuleEngine
from engines.score_engine import ScoreEngine
from engines.risk_engine import RiskEngine
from engines.decision_engine import DecisionEngine


def run_decision_pipeline(market_data: dict, volatility: float):
    """Run the complete decision pipeline"""

    print("=" * 50)
    print("  XFINLAB Core Decision System V1")
    print("=" * 50)

    # Step 1: Rule Engine
    rule_engine = RuleEngine()
    rule_scores = rule_engine.evaluate(market_data)

    print("\n📊 [1] Market Data Input:")
    for key, value in market_data.items():
        print(f"     {key}: {value}")

    print("\n📋 [2] Rule Scores:")
    for rule, score in rule_scores.items():
        print(f"     {rule}: +{score}")

    # Step 2: Score Engine
    score_engine = ScoreEngine()
    score_result = score_engine.calculate(rule_scores)

    print("\n🎯 [3] Total Score:")
    print(f"     Total Score  : {score_result['total_score']} / 100")
    print(f"     Score %      : {score_result['score_percent']}%")

    # Step 3: Risk Engine
    risk_engine = RiskEngine()
    risk_result = risk_engine.assess(volatility)

    print("\n⚠️  [4] Risk Assessment:")
    print(f"     Volatility   : {risk_result['volatility']}")
    print(f"     Risk Level   : {risk_result['risk_level']}")

    # Step 4: Decision Engine
    decision_engine = DecisionEngine()
    decision_result = decision_engine.decide(score_result)

    print("\n✅ [5] Final Decision:")
    print(f"     Decision     : {decision_result['decision']}")
    print("=" * 50)

    return decision_result


if __name__ == "__main__":

    # Test Case 1: All conditions met (Strong Buy)
    print("\n🧪 TEST CASE 1: All Bullish Conditions")
    market_data_1 = {
        "volume_ratio": 2.5,
        "trend": "bullish",
        "breakout": True,
        "sentiment": "bullish",
    }
    run_decision_pipeline(market_data_1, volatility=15)

    # Test Case 2: Partial conditions (Neutral)
    print("\n🧪 TEST CASE 2: Partial Conditions")
    market_data_2 = {
        "volume_ratio": 1.5,  # Below threshold, no score
        "trend": "bullish",  # +30
        "breakout": False,  # No score
        "sentiment": "bearish",  # No score
    }
    run_decision_pipeline(market_data_2, volatility=25)

    # Test Case 3: No conditions met (Bearish)
    print("\n🧪 TEST CASE 3: Bearish Conditions")
    market_data_3 = {
        "volume_ratio": 1.0,
        "trend": "bearish",
        "breakout": False,
        "sentiment": "bearish",
    }
    run_decision_pipeline(market_data_3, volatility=55)
