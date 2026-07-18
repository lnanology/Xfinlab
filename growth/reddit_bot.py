import os
import sys
import time
import requests
import re
sys.path.insert(0, "/Users/aj/Desktop/Xfinlab-main")

from dotenv import load_dotenv
load_dotenv()


class RedditBot:
    """
    XFINLAB Reddit Bot - Monitor Reddit stock discussions.

    2026-07-18 compliance fix: this used to spoof a Chrome browser
    User-Agent to hit Reddit's unauthenticated /r/{sub}/hot.json endpoint
    -- exactly the "pretend to be a browser" pattern real API-compliance
    guidance flags as unacceptable. Reddit's own API rules actually
    require the opposite: a descriptive, unique User-Agent identifying
    your app and contact (https://github.com/reddit-archive/reddit/wiki/API),
    even for the unauthenticated JSON endpoints -- Reddit rate-limits (and
    can ban) generic/spoofed User-Agents more aggressively. Switched to an
    honest identifying UA, added a delay between subreddit requests, and
    429/503 backoff instead of silently giving up on the first bad status.

    NOT done here (bigger, separate lift than a compliance fix): migrating
    to Reddit's official OAuth API (via e.g. the `praw` library) properly
    authenticates as a registered app and gets a real, documented rate
    limit instead of relying on the best-effort unauthenticated endpoint --
    worth doing before this bot runs at any real scale, but needs a Reddit
    app registration (client id/secret) this session doesn't have.
    """

    HEADERS = {
        "User-Agent": "XFINLABBot/1.0 (stock-sentiment research; contact: support@xfinlab.com)",
        "Accept": "application/json",
        "Accept-Language": "en-US,en;q=0.9",
    }

    # Reddit's unauthenticated endpoints don't publish a documented rate
    # limit the way the OAuth API does -- this is a conservative, honest
    # guess (well under 1 req/sec) rather than hammering it back-to-back
    # across 6 subreddits.
    REQUEST_DELAY_SECONDS = 2.0
    BACKOFF_SECONDS = 30

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
    def get_hot_posts(subreddit: str, limit: int = 10, _retry: bool = True) -> list:
        try:
            url = f"https://www.reddit.com/r/{subreddit}/hot.json?limit={limit}&raw_json=1"
            session = requests.Session()
            session.headers.update(RedditBot.HEADERS)
            res = session.get(url, timeout=15)

            if res.status_code in (429, 503) and _retry:
                # Back off once and retry rather than either hammering
                # again immediately or silently dropping the subreddit.
                print(f"  r/{subreddit}: HTTP {res.status_code}, backing off {RedditBot.BACKOFF_SECONDS}s then retrying once")
                time.sleep(RedditBot.BACKOFF_SECONDS)
                return RedditBot.get_hot_posts(subreddit, limit=limit, _retry=False)

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
        for i, subreddit in enumerate(RedditBot.SUBREDDITS):
            if i > 0:
                time.sleep(RedditBot.REQUEST_DELAY_SECONDS)
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
