
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.cache import Cache
from quant.factor_engine import FactorEngine
from quant.tensor_network import TensorNetwork

from ai.agents.news_agent import NewsAgent
from ai.agents.risk_agent import RiskAgent
from ai.agents.strategy_agent import StrategyAgent
from ai.agents.judge_agent import JudgeAgent

from trading.signal_engine import SignalEngine
from trading.paper_trader import PaperTrader

from alpha.feature_engine import FeatureEngine
from alpha.alpha_engine import AlphaEngine
from alpha.regime_detector import RegimeDetector

from agents.ceo_agent import CEOAgent
from agents.analyst_agent import AnalystAgent
from agents.risk_agent_v2 import RiskAgentV2
from agents.portfolio_agent import PortfolioAgent
from agents.committee import Committee

from agi.learning_loop import LearningLoop


class MasterPipeline:
    # 2026-07-18 fix: `trader` used to be a single PaperTrader() instance
    # shared as a CLASS attribute -- every ticker, every user, across the
    # whole server process's lifetime, all mutated the SAME cash/position
    # dict. A request for AAPL could show paper-trading state left over
    # from an unrelated NVDA request five minutes earlier from a
    # different user. Not currently exposed to end users (api/
    # pipeline_api.py's _to_probability_view() never reads raw["paper_
    # trading"]), but it's a real correctness bug in the internal result,
    # not just an unvalidated formula -- fixed by creating a fresh
    # PaperTrader() per pipeline run instead of sharing one across every
    # call.
    agi = LearningLoop()

    @staticmethod
    def run(ticker: str, market_data: dict, news_data: list):
        cached = Cache.get(f"master:{ticker}")
        if cached:
            return cached

        trader = PaperTrader()

        # L2: Factor + Quant
        factor = FactorEngine.calculate(market_data)
        tensor = TensorNetwork.compute(market_data.get("matrix", [[1,2,3],[2,3,4]]))

        # L3: AI Agents
        news = NewsAgent.analyze(news_data)
        risk = RiskAgent.analyze(market_data.get("volatility", 50), market_data.get("event_risk", 50), news["score"])
        strategy = StrategyAgent.analyze(market_data)
        decision = JudgeAgent.decide(news, risk, strategy)

        # L5: Trading
        signal = SignalEngine.generate(decision)
        paper = trader.execute(ticker, signal, market_data.get("price", 100))

        # L6: Alpha
        features = FeatureEngine.build(market_data)
        alpha = AlphaEngine.generate(features)
        # Step 2 of the Strategy Intelligence roadmap (2026-07-18): classify()
        # returns the same regime string detect() always did, PLUS
        # secondary_flags (e.g. LOW_LIQUIDITY, TREND_REVERSAL_WATCH) derived
        # from real Confluence/Market Structure Engine signals now passed
        # through in market_data. Purely additive -- `regime` is unchanged.
        regime_info = RegimeDetector.classify(market_data)
        regime = regime_info["regime"]
        regime_secondary_flags = regime_info["secondary_flags"]

        # L8: Fund Committee
        ceo = CEOAgent.decide(market_data)
        analyst = AnalystAgent.analyze(market_data)
        risk_v2 = RiskAgentV2.evaluate(market_data.get("volatility", 50))
        portfolio_alloc = PortfolioAgent.allocate(risk_v2, analyst)
        committee = Committee.vote(ceo, analyst, risk_v2, portfolio_alloc)

        # L10: AGI
        agi_result = MasterPipeline.agi.run({
            "market_score": market_data.get("score", 50),
            "strategy_score": decision["final_score"]
        })

        result = {
            "ticker": ticker,
            "level": "L1-L10 Master Pipeline",
            "factor": factor,
            "tensor": tensor,
            "news": news,
            "risk": risk,
            "strategy": strategy,
            "decision": decision,
            "signal": signal,
            "paper_trading": paper,
            "alpha": alpha,
            "regime": regime,
            "regime_secondary_flags": regime_secondary_flags,
            "committee": committee,
            "agi": agi_result
        }

        Cache.set(f"master:{ticker}", result, ttl=300)
        return result
