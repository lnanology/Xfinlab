import os
import sys
import requests
import re
sys.path.insert(0, "/Users/aj/Desktop/Xfinlab-main")

from dotenv import load_dotenv
load_dotenv()


class RedditBot:
    """XFINLAB Reddit Bot - Monitor Reddit stock discussions"""

    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Accept-Language": "en-US,en;q=0.9",
    }

    SUBREDDITS = [
        "stocks", "investing", "wallstreetbets",
        "SecurityAnalysis", "StockMarket", "options"
    ]

    WATCHLIST = [
        "AAPL", "NVDA", "TSLA", "MSFT", "META",
        "AMZN", "GOOGL", "AMD", "PLTR", "NFLX",
        "COIN", "MSTR", "SOFI", "RIVN", "GME", "AMC"
    ]

    @staticmethod
    def get_hot_posts(subreddit: str, limit: int = 10) -> list:
        try:
            url = f"https://www.reddit.com/r/{subreddit}/hot.json?limit={limit}&raw_json=1"
            session = requests.Session()
            session.headers.update(RedditBot.HEADERS)
            res = session.get(url, timeout=15)

            if res.status_code != 200:
                print(f"  r/{subreddit}: HTTP {res.status_code}")
                return []

            data = res.json()
            posts = []
            for post in data["data"]["children"]:
                p = post["data"]
                posts.append({
                    "title": p.get("title", ""),
                    "score": p.get("score", 0),
                    "comments": p.get("num_comments", 0),
                    "url": f"https://reddit.com{p.get('permalink', '')}",
                    "subreddit": subreddit
                })
            return posts
        except Exception as e:
            print(f"  r/{subreddit}: {e}")
            return []

    @staticmethod
    def find_stock_mentions(posts: list) -> dict:
        mentions = {}
        for post in posts:
            text = post["title"].upper()
            for ticker in RedditBot.WATCHLIST:
                pattern = rf'\b{ticker}\b'
                if re.search(pattern, text):
                    if ticker not in mentions:
                        mentions[ticker] = {"count": 0, "posts": [], "total_score": 0}
                    mentions[ticker]["count"] += 1
                    mentions[ticker]["posts"].append(post["title"][:60])
                    mentions[ticker]["total_score"] += post["score"]

        return dict(sorted(mentions.items(), key=lambda x: x[1]["count"], reverse=True))

    @staticmethod
    def get_sentiment_summary() -> dict:
        all_posts = []
        for subreddit in RedditBot.SUBREDDITS:
            posts = RedditBot.get_hot_posts(subreddit, limit=15)
            all_posts.extend(posts)
            print(f"  r/{subreddit}: {len(posts)} posts")

        mentions = RedditBot.find_stock_mentions(all_posts)
        return {
            "total_posts_analyzed": len(all_posts),
            "subreddits": RedditBot.SUBREDDITS,
            "top_mentions": mentions
        }


if __name__ == "__main__":
    print("XFINLAB Reddit Bot - Scanning...\n")
    result = RedditBot.get_sentiment_summary()

    print(f"\nTotal posts analyzed: {result['total_posts_analyzed']}")
    print("\nTop Stock Mentions:")

    for ticker, data in list(result["top_mentions"].items())[:10]:
        print(f"  {ticker}: {data['count']} mentions | Score: {data['total_score']}")
        for post in data["posts"][:2]:
            print(f"    - {post}")
