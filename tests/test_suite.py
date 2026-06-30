"""
XFINLAB Test Suite
Run: pytest tests/ -v
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from engines.rule_engine import RuleEngine
from engines.score_engine import ScoreEngine
from engines.risk_engine import RiskEngine
from engines.decision_engine import DecisionEngine
from engines.event_engine import EventEngine
from services.crypto_service import CryptoService


# ============================================================
# RuleEngine Tests
# ============================================================


class TestRuleEngine:

    def setup_method(self):
        self.engine = RuleEngine()

    def test_all_rules_triggered(self):
        data = {
            "volume_ratio": 2.5,
            "trend": "bullish",
            "breakout": True,
            "sentiment": "bullish",
        }
        result = self.engine.evaluate(data)
        assert result["volume_spike"] == 20.0
        assert result["trend_up"] == 30.0
        assert result["breakout"] == 25.0
        assert result["bullish_sentiment"] == 25.0

    def test_no_rules_triggered(self):
        data = {
            "volume_ratio": 1.0,
            "trend": "bearish",
            "breakout": False,
            "sentiment": "bearish",
        }
        result = self.engine.evaluate(data)
        assert result == {}

    def test_partial_rules(self):
        data = {
            "volume_ratio": 1.0,
            "trend": "bullish",
            "breakout": False,
            "sentiment": "bearish",
        }
        result = self.engine.evaluate(data)
        assert "trend_up" in result
        assert "volume_spike" not in result

    def test_volume_ratio_boundary(self):
        # Exactly 2.0 should NOT trigger (must be > 2)
        data = {
            "volume_ratio": 2.0,
            "trend": "bearish",
            "breakout": False,
            "sentiment": "bearish",
        }
        result = self.engine.evaluate(data)
        assert "volume_spike" not in result

        # 2.01 should trigger
        data["volume_ratio"] = 2.01
        result = self.engine.evaluate(data)
        assert "volume_spike" in result


# ============================================================
# ScoreEngine Tests
# ============================================================


class TestScoreEngine:

    def setup_method(self):
        self.engine = ScoreEngine()

    def test_full_score(self):
        rule_scores = {
            "volume_spike": 20.0,
            "trend_up": 30.0,
            "breakout": 25.0,
            "bullish_sentiment": 25.0,
        }
        result = self.engine.calculate(rule_scores)
        assert result["total_score"] == 100.0
        assert result["score_percent"] == 100.0

    def test_zero_score(self):
        result = self.engine.calculate({})
        assert result["total_score"] == 0
        assert result["score_percent"] == 0.0

    def test_partial_score(self):
        rule_scores = {"trend_up": 30.0}
        result = self.engine.calculate(rule_scores)
        assert result["total_score"] == 30.0
        assert result["score_percent"] == 30.0


# ============================================================
# RiskEngine Tests
# ============================================================


class TestRiskEngine:

    def setup_method(self):
        self.engine = RiskEngine()

    def test_low_risk(self):
        result = self.engine.assess(15)
        assert result["risk_level"] == "Low Risk"

    def test_medium_risk(self):
        result = self.engine.assess(30)
        assert result["risk_level"] == "Medium Risk"

    def test_high_risk(self):
        result = self.engine.assess(55)
        assert result["risk_level"] == "High Risk"

    def test_boundary_20(self):
        result = self.engine.assess(20)
        assert result["risk_level"] == "Medium Risk"

    def test_boundary_40(self):
        result = self.engine.assess(40)
        assert result["risk_level"] == "Medium Risk"


# ============================================================
# DecisionEngine Tests
# ============================================================


class TestDecisionEngine:

    def setup_method(self):
        self.engine = DecisionEngine()

    def test_strong_buy(self):
        result = self.engine.decide({"total_score": 100})
        assert result["decision"] == "Strong Buy"

    def test_bullish(self):
        result = self.engine.decide({"total_score": 70})
        assert result["decision"] == "Bullish"

    def test_neutral(self):
        result = self.engine.decide({"total_score": 50})
        assert result["decision"] == "Neutral"

    def test_bearish(self):
        result = self.engine.decide({"total_score": 20})
        assert result["decision"] == "Bearish"

    def test_boundary_80(self):
        result = self.engine.decide({"total_score": 80})
        assert result["decision"] == "Strong Buy"

    def test_boundary_60(self):
        result = self.engine.decide({"total_score": 60})
        assert result["decision"] == "Bullish"


# ============================================================
# EventEngine Tests
# ============================================================


class TestEventEngine:

    def setup_method(self):
        self.engine = EventEngine()

    def test_find_earnings_events(self):
        events = self.engine.find_similar_events("earnings")
        assert isinstance(events, list)
        assert len(events) > 0

    def test_find_unknown_event_type(self):
        events = self.engine.find_similar_events("unknown_type")
        assert events == []

    def test_average_reaction_empty(self):
        result = self.engine.calculate_average_reaction([])
        assert result["avg_1d"] == 0.0
        assert result["avg_7d"] == 0.0
        assert result["avg_30d"] == 0.0

    def test_success_rate_empty(self):
        result = self.engine.calculate_success_rate([])
        assert result == 0.0

    def test_full_analysis(self):
        result = self.engine.analyze("earnings")
        assert "historical_cases" in result
        assert "avg_reaction" in result
        assert "success_rate" in result
        assert "market_impact_score" in result
        assert result["historical_cases"] > 0


# ============================================================
# CryptoService Tests
# ============================================================


class TestCryptoService:

    def setup_method(self):
        self.service = CryptoService()

    def test_bitcoin(self):
        result = self.service.get_crypto_data("bitcoin")
        assert result is not None
        assert result["symbol"] == "BTC"
        assert result["price"] > 0
        assert result["market_cap"] > 0
        assert result["volume_24h"] > 0

    def test_ethereum(self):
        result = self.service.get_crypto_data("ethereum")
        assert result is not None
        assert result["symbol"] == "ETH"

    def test_invalid_symbol(self):
        result = self.service.get_crypto_data("invalidcoin99999")
        assert result is None

    def test_ticker_input(self):
        result = self.service.get_crypto_data("BTC")
        assert result is not None
        assert result["symbol"] == "BTC"
