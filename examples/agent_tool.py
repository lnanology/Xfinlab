"""Wrap XFINLAB as a plain function tool for any agent framework.
With LangChain: from langchain_core.tools import tool; decorate `xfinlab_technical` with @tool."""
import os, requests

BASE = "https://api.xfinlab.com/api/intelligence/v1"


def xfinlab_technical(ticker: str) -> str:
    """Technical analysis (trend, momentum, confidence) for a stock ticker."""
    r = requests.get(f"{BASE}/technical/{ticker}", headers={"X-API-Key": os.environ["XFINLAB_API_KEY"]}, timeout=30)
    if r.status_code == 429:
        return "Quota reached for today."
    r.raise_for_status()
    return r.text
