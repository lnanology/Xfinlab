import sys
sys.path.insert(0, "/Users/aj/Desktop/Xfinlab-main")

from dotenv import load_dotenv
from ai.ai_router import get_ai_response
load_dotenv()


class FacebookGenerator:
    @staticmethod
    def generate_daily_post() -> str:
        prompt = (
            "你是 XFINLAB AI 投資平台社交媒體管理員。"
            "生成吸引人的 Facebook 帖子，今日股票市場分析。"
            "格式：吸引標題(emoji)+3-4重點+CTA加入Telegram+hashtag。"
            "150-200字繁體中文。"
            "Telegram:t.me/xfinlab_zh 網站:xfinlab.com。"
            "只回覆帖子文字。"
        )
        return get_ai_response(prompt, max_tokens=500)

    @staticmethod
    def generate_stock_post(ticker: str, price: float = None) -> str:
        price_info = f"現價${price}" if price else ""
        prompt = (
            f"生成{ticker}{price_info}的Facebook帖子。"
            "格式：標題+分析+AI評級+風險提示+CTA+hashtag。"
            "150-200字繁體中文，加入t.me/xfinlab_zh和xfinlab.com。"
            "只回覆帖子文字。"
        )
        return get_ai_response(prompt, max_tokens=500)

    @staticmethod
    def generate_promotion_post() -> str:
        prompt = (
            "生成推廣XFINLAB平台的Facebook帖子。"
            "重點：AI分析、免費使用、Telegram免費訊號、多語言。"
            "格式：標題+3個優勢+免費試用CTA+hashtag。"
            "150-200字繁體中文。"
            "網站:xfinlab.com Telegram:t.me/xfinlab_zh。"
            "只回覆帖子文字。"
        )
        return get_ai_response(prompt, max_tokens=500)

    @staticmethod
    def generate_weekly_summary() -> str:
        prompt = (
            "生成每週市場總結Facebook帖子。"
            "格式：本週亮點+下週展望+推薦股票+CTA+hashtag。"
            "200-250字繁體中文，加入t.me/xfinlab_zh和xfinlab.com。"
            "只回覆帖子文字。"
        )
        return get_ai_response(prompt, max_tokens=600)


if __name__ == "__main__":
    print("XFINLAB Facebook Generator\n")
    print("=" * 50)
    print("【今日市場分析】")
    print("=" * 50)
    print(FacebookGenerator.generate_daily_post())
    print("\n" + "=" * 50)
    print("【AAPL 分析】")
    print("=" * 50)
    print(FacebookGenerator.generate_stock_post("AAPL", 298.01))
    print("\n" + "=" * 50)
    print("【平台推廣】")
    print("=" * 50)
    print(FacebookGenerator.generate_promotion_post())
