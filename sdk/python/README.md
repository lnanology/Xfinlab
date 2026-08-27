# xfinlab-intelligence (Python)

Official Python client for the [XFINLAB Intelligence API](https://www.xfinlab.com/intelligence-api.html) -- structured market events, FinBERT sentiment, multi-agent AI debate, an AI-clustered intelligence feed, technical/market-structure analysis, and Monte Carlo stress testing.

Not yet on PyPI (no paying developers on the API yet to justify maintaining a public package release). Install directly from this repo instead:

```bash
pip install "git+https://github.com/lnanology/Xfinlab.git#subdirectory=sdk/python"
```

Or just copy `xfinlab_intelligence/__init__.py` into your own project -- it has zero internal imports.

## Get a key

Free tier keys are issued instantly, no waiting: https://www.xfinlab.com/intelligence-api.html

## Quickstart

```python
from xfinlab_intelligence import XfinlabClient

client = XfinlabClient(api_key="xfl_...")

# Recent headlines for a ticker
events = client.events(ticker="AAPL", limit=10)

# FinBERT sentiment across recent headlines
sentiment = client.sentiment("AAPL")

# Confluence / trend / MACD / market structure
technical = client.technical("AAPL", period="6mo")

# Real historical-bootstrap Monte Carlo simulation
stress = client.stress_test("AAPL", amount=10000, horizon_days=252)

# Pro/Enterprise only: 4-call Bull/Bear/Risk-Manager AI debate
debate = client.debate("AAPL")

# AI-clustered intelligence feed (entities, sentiment, cross-asset reads, narrative)
feed = client.intel_for_ticker("AAPL", limit=5)
```

## Error handling

Every method raises `XfinlabError` (with a `.status_code` attribute) on a non-2xx response or an explicit `{"success": false}` from the API -- including `429` when you've hit your daily quota.

```python
from xfinlab_intelligence import XfinlabClient, XfinlabError

client = XfinlabClient(api_key="xfl_...")
try:
    result = client.debate("AAPL")
except XfinlabError as e:
    print(f"Request failed ({e.status_code}): {e}")
```

## API reference

| Method | Endpoint | Notes |
|---|---|---|
| `status()` | `GET /intelligence/status` | Public, no key required |
| `events(ticker=None, limit=20)` | `GET /v1/events` | |
| `sentiment(ticker, limit=10)` | `GET /v1/sentiment` | |
| `debate(ticker)` | `GET /v1/debate` | Weighted 5x in quota |
| `intel_latest(limit=5, lang="zh-HK")` | `GET /v1/intel/latest` | Weighted 8x in quota |
| `intel_for_ticker(ticker, limit=5, lang="zh-HK")` | `GET /v1/intel/{ticker}` | Weighted 8x in quota |
| `technical(ticker, period="6mo", interval="1d", lang="en")` | `GET /v1/technical/{ticker}` | Weighted 3x in quota |
| `stress_test(symbol, amount, horizon_days=252, n_simulations=None, lang=None)` | `POST /v1/stress-test` | Weighted 3x in quota |
| `regime_signal(ticker, regime=None, min_trades=5)` | `GET /v1/regime-signal/{ticker}` | Weighted 3x in quota |
| `forecast(ticker, horizon_days=5, n_simulations=None)` | `GET /v1/forecast/{ticker}` | Weighted 4x in quota |
| `insider(ticker)` | `GET /v1/insider/{ticker}` | Weighted 3x in quota |
| `short_interest(ticker)` | `GET /v1/short-interest/{ticker}` | Weighted 2x in quota |
| `energy(ticker)` | `GET /v1/energy/{ticker}` | Weighted 2x in quota |
| `exchange(ticker)` | `GET /v1/exchange/{ticker}` | Weighted 2x in quota |

Full endpoint docs, pricing tiers, and quota weighting: https://www.xfinlab.com/intelligence-api.html

## License

MIT -- see `../LICENSE`.
