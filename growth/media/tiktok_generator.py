import sys
sys.path.insert(0, "/Users/aj/Desktop/Xfinlab-main")

from dotenv import load_dotenv
from ai.ai_router import get_ai_response
load_dotenv()


class TikTokGenerator:
    """Generate TikTok scripts for XFINLAB"""

    @staticmethod
    def generate_script(ticker: str, analysis: dict = None) -> str:
        price = analysis.get("price", "N/A") if analysis else "N/A"
        score = analysis.get("final_score", "N/A") if analysis else "N/A"
        rating = analysis.get("rating", "N/A") if analysis else "N/A"

        prompt = (
            f"Write a viral TikTok script (30-45 seconds) about {ticker} stock. "
            f"Price: ${price}, AI Score: {score}/100, Rating: {rating}. "
            "Format: Hook (3s) → Surprising fact (10s) → AI data (15s) → CTA (5s). "
            "Style: Gen-Z friendly, casual, use emojis. "
            "Hook must be attention-grabbing (e.g. 'Wait until you see this...'). "
            "End with: Follow for daily AI stock picks. "
            "Include [TEXT ON SCREEN] and [SOUND] notes. "
            "Respond with script only."
        )
        return get_ai_response(prompt, max_tokens=400)

    @staticmethod
    def generate_trending_topic() -> str:
        prompt = (
            "Write a viral TikTok script (30-45 seconds) about AI investing and stock analysis. "
            "Style: Trendy, use Gen-Z language, emojis, casual tone. "
            "Hook: Something surprising about AI and stocks. "
            "End with: XFINLAB gives you AI analysis for free. Link in bio. "
            "Include [TEXT ON SCREEN] and [SOUND] notes. "
            "Respond with script only."
        )
        return get_ai_response(prompt, max_tokens=400)


if __name__ == "__main__":
    print("XFINLAB TikTok Generator\n")

    print("── Trending Topic Script ──")
    script = TikTokGenerator.generate_trending_topic()
    print(script)

    print("\n── TSLA Script ──")
    script = TikTokGenerator.generate_script("TSLA", {"price": 400.49, "final_score": 55, "rating": "Neutral"})
    print(script)
