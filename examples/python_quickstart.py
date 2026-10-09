"""pip install requests ; XFINLAB_API_KEY=xfl_... python python_quickstart.py AAPL"""
import os, sys, requests

BASE = "https://api.xfinlab.com/api/intelligence/v1"
KEY = os.environ["XFINLAB_API_KEY"]


def get(path, **params):
    r = requests.get(f"{BASE}/{path}", headers={"X-API-Key": KEY}, params=params, timeout=30)
    if r.status_code == 429:
        print("Daily quota reached:", r.json().get("detail"))
        sys.exit(1)
    r.raise_for_status()
    print("remaining today:", r.headers.get("X-RateLimit-Remaining"))
    return r.json()


if __name__ == "__main__":
    t = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    print(get(f"technical/{t}"))
    print(get("sentiment", ticker=t, limit=5))
