import os
import sys
sys.path.insert(0, "/Users/aj/Desktop/Xfinlab-main")

from dotenv import load_dotenv
from ai.ai_router import get_ai_response
load_dotenv()


class LinkedInGenerator:
    """Generate professional LinkedIn posts for XFINLAB"""

    @staticmethod
    def generate_post(ticker: str, analysis: dict = None) -> str:
        price = analysis.get("price", "N/A") if analysis else "N/A"
        score = analysis.get("final_score", "N/A") if analysis else "N/A"
        rating = analysis.get("rating", "N/A") if analysis else "N/A"

        prompt = (
            f"Write a professional LinkedIn post about {ticker} stock analysis. "
            f"Price: ${price}, AI Score: {score}/100, Rating: {rating}. "
            "Style: Professional, insightful, 150-200 words. "
            "Include 3-5 relevant hashtags at the end. "
            "Mention XFINLAB AI platform. "
            "Do NOT give financial advice. "
            "Respond with the post text only."
        )

        return get_ai_response(prompt, max_tokens=400)

    @staticmethod
    def generate_daily_market_post() -> str:
        prompt = (
            "Write a professional LinkedIn post about today's stock market. "
            "Cover: market sentiment, key sectors, AI investing trends. "
            "Style: Thought leadership, 150-200 words. "
            "Include hashtags: #investing #stockmarket #AI #XFINLAB "
            "Respond with post text only."
        )
        return get_ai_response(prompt, max_tokens=400)


if __name__ == "__main__":
    print("XFINLAB LinkedIn Generator\n")

    print("── Daily Market Post ──")
    post = LinkedInGenerator.generate_daily_market_post()
    print(post)

    print("\n── AAPL Analysis Post ──")
    post = LinkedInGenerator.generate_post("AAPL", {"price": 298.01, "final_score": 61, "rating": "Neutral"})
    print(post)
