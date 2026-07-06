import os
import requests
from dotenv import load_dotenv

load_dotenv()

DIFY_API_KEY = os.getenv("DIFY_API_KEY")
DIFY_API_URL = os.getenv("DIFY_API_URL", "https://api.dify.ai/v1")


class DifyService:
    """XFINLAB DIFY Integration - ITSPossible Chat"""

    @staticmethod
    def chat(query: str, user_id: str = "xfinlab-user", conversation_id: str = None) -> dict:
        headers = {
            "Authorization": f"Bearer {DIFY_API_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "inputs": {},
            "query": query,
            "response_mode": "blocking",
            "user": user_id
        }
        if conversation_id:
            payload["conversation_id"] = conversation_id

        try:
            res = requests.post(
                f"{DIFY_API_URL}/chat-messages",
                headers=headers,
                json=payload,
                timeout=30
            )
            data = res.json()
            return {
                "status": "ok",
                "answer": data.get("answer", ""),
                "conversation_id": data.get("conversation_id", ""),
                "message_id": data.get("id", "")
            }
        except Exception as e:
            return {"status": "error", "answer": str(e)}

    @staticmethod
    def analyze_stock(ticker: str, market_data: dict = None) -> dict:
        price = market_data.get("price", "N/A") if market_data else "N/A"
        query = (
            f"請分析 {ticker} 股票，現價 ${price}。"
            f"提供：市場趨勢分析、投資建議、風險評估、目標價位。"
            f"用繁體中文回答，專業簡潔。"
        )
        return DifyService.chat(query)
