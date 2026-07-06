
from engines.news_engine import NewsEngine
from engines.risk_engine import RiskEngine
from engines.scoring_engine import ScoringEngine
from engines.strategy_engine import StrategyEngine
from engines.portfolio_engine import PortfolioEngine

class Pipeline:
    @staticmethod
    def run(ticker: str, market_data: dict, news_data: list):
        strategy_score = StrategyEngine.analyze(market_data)
        news_result = NewsEngine.analyze(news_data)
        news_score = news_result.get("score", 50)
        risk_result = RiskEngine.calculate(
            volatility=market_data.get("volatility", 50),
            event_risk=market_data.get("event_risk", 50),
            news_score=news_score
        )
        market_score = market_data.get("score", 50)
        final_result = ScoringEngine.calculate(
            market_score=market_score,
            news_score=news_score,
            strategy_score=strategy_score,
            overall_risk=risk_result["overall_risk"]
        )
        portfolio = PortfolioEngine.allocate(
            final_score=final_result["final_score"],
            ticker=ticker
        )
        return {
            "ticker": ticker,
            "market_score": market_score,
            "strategy_score": strategy_score,
            "news": news_result,
            "risk": risk_result,
            "final": final_result,
            "portfolio": portfolio
        }
