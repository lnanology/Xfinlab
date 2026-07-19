import os
import sys
import time
import requests
import re

# 2026-07-19: was a hardcoded "/Users/aj/Desktop/Xfinlab-main" -- only
# worked on that one machine's local path. Needed a real fix now (not
# just when this script is run directly) because the new FinBERT import
# below depends on the repo root actually being on sys.path in whatever
# environment runs this (sandbox, Railway, or a dev laptop).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from services.finbert_sentiment_service import analyze_batch as finbert_analyze_batch


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
    def score_sentiment(mentions: dict) -> dict:
        """
        2026-07-19 Stage 2 roadmap fix ("升級...社交情緒引擎"): despite its
        name, get_sentiment_summary() never actually scored sentiment --
        it only counted ticker MENTIONS and summed Reddit's own upvote
        "score" field, neither of which is a polarity measure (a ticker
        can be mentioned heavily in an angry or bearish thread and still
        rack up mentions/upvotes). This runs the same real
        services/finbert_sentiment_service.py used for the News Engine
        over each ticker's collected post titles and attaches a genuine
        bullish/neutral/bearish read.

        Mutates and returns `mentions` in place, adding per-ticker
        "sentiment_available", and when available: "sentiment_score"
        (0-100), "sentiment_label", "sentiment_method". When FinBERT
        isn't configured/reachable, sentiment_available is honestly set
        to False for every ticker -- this NEVER fabricates a polarity
        from the mention/upvote counts as a substitute.

        Note: this is unrelated to (and doesn't change) the open Reddit
        Data API compliance gap documented in
        services/license_registry.py's "reddit_unauthenticated" entry --
        this bot still isn't wired into any live XFINLAB endpoint, and
        migrating to the official OAuth API (via `praw`) remains a
        separate, not-yet-done task needing Reddit developer credentials.
        """
        if not mentions:
            return mentions

        # One batched FinBERT call across every ticker's posts (cheaper
        # and faster than one call per ticker), then redistribute results
        # back by tracking each text's (ticker, index) origin.
        all_texts = []
        origin = []  # parallel list: (ticker, position_in_that_tickers_posts)
        for ticker, data in mentions.items():
            for post_title in data["posts"]:
                all_texts.append(post_title)
                origin.append(ticker)

        finbert_result = finbert_analyze_batch(all_texts) if all_texts else {"available": False}

        if not finbert_result.get("available"):
            for data in mentions.values():
                data["sentiment_available"] = False
            return mentions

        per_ticker_scores: dict = {}
        for ticker, scored in zip(origin, finbert_result["results"]):
            per_ticker_scores.setdefault(ticker, []).append(scored["score"])

        for ticker, data in mentions.items():
            scores = per_ticker_scores.get(ticker, [])
            if not scores:
                data["sentiment_available"] = False
                continue
            avg = round(sum(scores) / len(scores), 1)
            data["sentiment_available"] = True
            data["sentiment_score"] = avg
            data["sentiment_label"] = "Bullish" if avg >= 60 else "Bearish" if avg <= 40 else "Neutral"
            data["sentiment_method"] = "finbert"

        return mentions

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
        RedditBot.score_sentiment(mentions)
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
        sentiment_note = (
            f" | Sentiment: {data['sentiment_label']} ({data['sentiment_score']}/100, FinBERT)"
            if data.get("sentiment_available") else " | Sentiment: unavailable (HF_API_TOKEN not configured)"
        )
        print(f"  {ticker}: {data['count']} mentions | Score: {data['total_score']}{sentiment_note}")
        for post in data["posts"][:2]:
            print(f"    - {post}")
