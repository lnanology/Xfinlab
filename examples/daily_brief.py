"""Print a one-screen brief for a watchlist.
XFINLAB_API_KEY=xfl_... python daily_brief.py AAPL MSFT NVDA"""
import os, sys, requests

BASE = "https://api.xfinlab.com/api/intelligence/v1"
H = {"X-API-Key": os.environ["XFINLAB_API_KEY"]}
tickers = sys.argv[1:] or ["AAPL", "MSFT", "NVDA"]

for t in tickers:
    r = requests.get(f"{BASE}/technical/{t}", headers=H, timeout=30)
    if r.status_code == 429:
        print("Quota reached; try again after midnight UTC."); break
    if not r.ok:
        print(f"{t}: error {r.status_code}"); continue
    d = r.json()
    print(f"{t}: {str(d)[:200]}")
