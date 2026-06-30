import os
import json
from dotenv import load_dotenv
from ai.ai_router import get_ai_response

load_dotenv()

class ResearchAgent:
    """XFINLAB Research Agent - AI-powered investment research"""

    @staticmethod
    def analyze(ticker: str, market_data: dict = None) -> dict:
        price = market_data.get("price", "N/A") if market_data else "N/A"
        market_score = market_data.get("market_score", "N/A") if market_data else "N/A"
        risk_score = market_data.get("risk_score", "N/A") if market_data else "N/A"

        prompt = (
            f"You are a professional investment analyst. "
            f"Generate a research report for {ticker}. "
            f"Price: {price}, Market Score: {market_score}/100, Risk Score: {risk_score}/100. "
            "Respond in valid JSON only with these keys: "
            "company_overview, financial_analysis, competitive_advantage, "
            "risk_factors, valuation, ai_recommendation, confidence, target_price, summary"
        )

        try:
            text = get_ai_response(prompt, max_tokens=1000)
            text = text.replace("```json", "").replace("```", "").strip()
            result = json.loads(text)
            result["ticker"] = ticker
            return result
        except Exception as e:
            return {
                "ticker": ticker,
                "error": str(e),
                "ai_recommendation": "HOLD",
                "confidence": 0,
                "summary": "Analysis unavailable"
            }
