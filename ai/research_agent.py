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

        # 2026-07-30 compliance fix: this prompt used to have zero guardrail
        # against the model literally writing "Buy"/"Sell"/"Strong Buy" into
        # ai_recommendation -- an unconstrained LLM field is the single
        # riskiest surface for accidentally producing investment-advice
        # wording, worse than a fixed enum because it can't be reviewed by
        # reading the code. Mirrors the instruction api/company_compare.py
        # already uses ("這是客觀資訊整理，不是投資建議，請勿使用「建議買入」
        # 「建議賣出」等字眼"): the field name (ai_recommendation) is kept
        # as-is so report_generator.py / dashboard.html don't need a schema
        # change, but the actual content it asks for is now an outlook
        # description, not a buy/sell instruction.
        prompt = (
            f"You are a professional financial data analyst. "
            f"Generate an objective research summary for {ticker}. "
            f"Price: {price}, Market Score: {market_score}/100, Risk Score: {risk_score}/100. "
            "Respond in valid JSON only with these keys: "
            "company_overview, financial_analysis, competitive_advantage, "
            "risk_factors, valuation, ai_recommendation, confidence, target_price, summary. "
            "This is an objective data summary, not investment advice -- for the "
            "ai_recommendation field, describe the overall outlook as Bullish/Neutral/"
            "Bearish with a one-sentence reason based on the data given. Do NOT use "
            "wording like 'Buy', 'Sell', 'Strong Buy', 'recommend buying', or "
            "'recommend selling' anywhere in the response."
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
                "ai_recommendation": "Neutral",
                "confidence": 0,
                "summary": "Analysis unavailable"
            }
