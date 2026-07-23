import sys
sys.path.insert(0, "/Users/aj/Desktop/Xfinlab-main")

from dotenv import load_dotenv
from ai.ai_router import get_ai_response
load_dotenv()


class YouTubeShortsGenerator:
    """Generate YouTube Shorts scripts for XFINLAB"""

    @staticmethod
    def generate_script(ticker: str, analysis: dict = None) -> str:
        price = analysis.get("price", "N/A") if analysis else "N/A"
        score = analysis.get("final_score", "N/A") if analysis else "N/A"
        rating = analysis.get("rating", "N/A") if analysis else "N/A"

        prompt = (
            f"Write a 60-second YouTube Shorts script about {ticker} stock. "
            f"Price: ${price}, AI Score: {score}/100, Rating: {rating}. "
            "Format: Hook (5s) → Key Data (20s) → AI Analysis (25s) → CTA (10s). "
            "Style: Energetic, engaging, simple language. "
            "End with: Check XFINLAB for full AI analysis. "
            "Include [VISUAL] notes for what to show on screen. "
            "Respond with script only."
        )
        return get_ai_response(prompt, max_tokens=500)

    @staticmethod
    def generate_market_overview() -> str:
        prompt = (
            "Write a 60-second YouTube Shorts script about today's stock market. "
            "Format: Hook (5s) → Top 3 movers (30s) → AI insight (15s) → CTA (10s). "
            "Style: Fast-paced, exciting. "
            "End with: Follow XFINLAB for daily AI market analysis. "
            "Include [VISUAL] notes. "
            "Respond with script only."
        )
        return get_ai_response(prompt, max_tokens=500)


if __name__ == "__main__":
    print("XFINLAB YouTube Shorts Generator\n")

    print("── Market Overview Script ──")
    script = YouTubeShortsGenerator.generate_market_overview()
    print(script)

    print("\n── NVDA Analysis Script ──")
    script = YouTubeShortsGenerator.generate_script("NVDA", {"price": 210.69, "final_score": 75, "rating": "Bullish"})
    print(script)
