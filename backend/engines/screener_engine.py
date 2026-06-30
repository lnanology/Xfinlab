from typing import List, Dict


class ScreenerEngine:
    """
    XFINLAB Screener Engine
    Filters and ranks stocks based on fundamental + AI scores
    """

    @staticmethod
    def screen(stocks: List[Dict]) -> Dict:
        """
        Args:
            stocks: List of stock data dicts
            Each stock must include:
            - ticker
            - market_score
            - news_score
            - strategy_score
            - risk_score

        Returns:
            Filtered and ranked list
        """

        results = []

        for stock in stocks:

            ticker = stock.get("ticker")

            market_score = stock.get("market_score", 0)
            news_score = stock.get("news_score", 0)
            strategy_score = stock.get("strategy_score", 0)
            risk_score = stock.get("risk_score", 100)

            # final screener score (reuse your scoring logic idea)
            final_score = (
                market_score * 0.3 +
                news_score * 0.25 +
                strategy_score * 0.3 +
                (100 - risk_score) * 0.15
            )

            # filtering rules (core value)
            if final_score < 60:
                continue

            if risk_score > 70:
                continue

            results.append({
                "ticker": ticker,
                "final_score": round(final_score, 2),
                "market_score": market_score,
                "news_score": news_score,
                "strategy_score": strategy_score,
                "risk_score": risk_score
            })

        # sort by best opportunities
        results.sort(key=lambda x: x["final_score"], reverse=True)

        return {
            "count": len(results),
            "results": results
        }