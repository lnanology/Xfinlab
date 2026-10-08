"""Runnable quickstart for the XFINLAB Intelligence API Python client.

Usage:
    pip install "git+https://github.com/lnanology/Xfinlab.git#subdirectory=sdk/python"
    XFINLAB_API_KEY=xfl_... python examples/python_quickstart.py

Get a free key (issued instantly): https://www.xfinlab.com/intelligence-api.html
"""
import os
import sys

from xfinlab_intelligence import XfinlabClient, XfinlabError


def main():
    api_key = os.environ.get("XFINLAB_API_KEY")
    if not api_key:
        print("Set XFINLAB_API_KEY in your environment first.", file=sys.stderr)
        print("Get a free key: https://www.xfinlab.com/intelligence-api.html", file=sys.stderr)
        sys.exit(1)

    client = XfinlabClient(api_key=api_key)

    print("== /intelligence/status (public, no key needed) ==")
    print(client.status())

    print("\n== Recent AAPL headlines ==")
    try:
        for item in client.events(ticker="AAPL", limit=5):
            print(f"- [{item['source']}] {item['title']}")
    except XfinlabError as e:
        print(f"events() failed ({e.status_code}): {e}")

    print("\n== AAPL sentiment (FinBERT) ==")
    try:
        sentiment = client.sentiment("AAPL")
        print(f"Average score: {sentiment.get('average_score')} "
              f"across {len(sentiment.get('results', []))} headlines")
    except XfinlabError as e:
        print(f"sentiment() failed ({e.status_code}): {e}")

    print("\n== AAPL technical / market structure ==")
    try:
        tech = client.technical("AAPL", period="6mo")
        confluence = tech.get("confluence", {})
        print(f"Confluence: {confluence.get('direction')} "
              f"({confluence.get('confidence')}% confidence)")
    except XfinlabError as e:
        print(f"technical() failed ({e.status_code}): {e}")


if __name__ == "__main__":
    main()
