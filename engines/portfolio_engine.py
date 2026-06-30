from typing import List, Dict

class PortfolioEngine:
    @staticmethod
    def allocate(stocks: List[Dict]) -> Dict:
        if not stocks:
            return {"portfolio": [], "cash": 100}
        total_score = sum(stock.get("final_score", 0) for stock in stocks)
        portfolio = []
        for stock in stocks:
            score = stock.get("final_score", 0)
            weight = round((score / total_score) * 100, 2)
            portfolio.append({"ticker": stock["ticker"], "allocation": weight})
        return {"portfolio": portfolio, "cash": 0}
