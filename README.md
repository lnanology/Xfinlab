# XFINLAB

**Financial Intelligence Infrastructure — APIs, SDKs, and an MCP server for developers and AI agents, plus a consumer research platform built on the same backend.**

Real market events, FinBERT sentiment, technical/market-structure analysis, SEC/CFTC/FDIC/USDA/CBOE official data, and Monte Carlo stress testing. Every field is traceable to a real computation or an official data source — nothing fabricated or interpolated.

[Architecture](./ARCHITECTURE.md) · [Get a free API key](https://www.xfinlab.com/intelligence-api.html) · [API docs](https://www.xfinlab.com/intelligence-api.html) · [llms.txt](https://www.xfinlab.com/llms.txt) · [Consumer product](https://www.xfinlab.com)

## Quick start (API)

```bash
pip install "git+https://github.com/lnanology/Xfinlab.git#subdirectory=sdk/python"
```

```python
from xfinlab_intelligence import XfinlabClient

client = XfinlabClient(api_key="xfl_...")  # free tier, issued instantly
sentiment = client.sentiment("AAPL")
technical = client.technical("AAPL", period="6mo")
fundamentals = client.fundamentals("AAPL")
```

Or JavaScript/Node:

```bash
npm install "github:lnanology/Xfinlab#path:sdk/js"
```

```js
const { XfinlabClient } = require('xfinlab-intelligence');
const client = new XfinlabClient('xfl_...');
const sentiment = await client.sentiment('AAPL');
```

19 endpoints total — market events, sentiment, AI debate, technical/market-structure, Monte Carlo stress testing, insider trading, institutional ownership, short interest, SEC XBRL fundamentals, CBOE VIX term structure, FDIC bank health, USDA agriculture, EIA energy, crypto, cross-region market map, and Pro-tier webhooks. Full reference: [intelligence-api.html](https://www.xfinlab.com/intelligence-api.html).

## MCP server (for Claude and other AI agents)

Every field this server returns is either a real computation/real official-source value, or `null` with an explanation — the MCP ecosystem has a lot of servers now, few of them say anything about the actual quality of the data behind the tool calls. This one does, in public: [xfinlab.com/trust.html](https://www.xfinlab.com/trust.html) shows every underlying data collector's live/down status in real time.

Already live in production — no setup needed, just point an MCP-compatible client at it:

```json
{
  "mcpServers": {
    "xfinlab": {
      "url": "https://api.xfinlab.com/api/mcp",
      "headers": { "X-API-Key": "xfl_..." }
    }
  }
}
```

Hosted service (the server implementation is proprietary and runs at `api.xfinlab.com`). Tools: `get_market_events`, `get_sentiment`, `get_technical_analysis`, `get_intelligence_feed`, `get_global_market_map`. Same auth and free tier as the REST API. Docs: [intelligence-api.html#mcp](https://www.xfinlab.com/intelligence-api.html#mcp).

## Production usage

*Early-stage, honest numbers — pulled from the platform's own admin metrics on 2026-09-22, not curated for effect. Individual emails aren't published here even though they're visible in the admin panel — no reason to expose real people's addresses in a public README.*

- **15 API keys issued** (14 active, 1 revoked) since the self-serve free tier launched, to roughly **13 distinct outside developers/researchers** — not counting the operator's own test key, which shows 0 calls, so none of the volume below is self-generated traffic.
- **669 weighted API calls served all-time**, concentrated in a small number of real integrations: the single heaviest account alone accounts for more than half of all-time volume, the second-heaviest for roughly another fifth.
- One signup used a `.edu` email address — an early, small signal of academic/research interest rather than only casual trials.
- **5 organic accounts** on the consumer research site (xfinlab.com), separate from the API-only signups above. Of 7 total registered accounts, 2 are the operator's own account and an internal LINE-bot integration, not external users — excluded from that count.
- No response-time or uptime SLA number is published here — it isn't actually measured yet, and this project holds itself to the same [zero-fabrication policy](https://www.xfinlab.com/trust.html) it markets to users, so an unmeasured number doesn't get invented for a case study either. Per-data-source status (not per-request latency) is live on that same page.

**Two real bugs this surfaced, fixed the same day each was found:**

- *SEC Form 4 false positives (Sept 2026).* SEC EDGAR's own `browse-edgar` `type` filter turned out to behave as a prefix wildcard, not an exact match — `type=4` was silently matching unrelated `424B`-series filings as "insider trading" activity. Caught by the platform's own data-source health alerting (not a user bug report), confirmed against SEC's live responses — its own pagination link rewrites `type=4` to `type=4%25`, which is what gave the bug away.
- *Point-in-time/vintage data store (Sept 2026).* A quant researcher's comment on r/quant pointed out that treating a filing's period-end date as "known on that date" ignores real filing lag and later restatements — a classic look-ahead-bias source in backtests. Built a dedicated (proprietary) store where every fundamentals value carries a real filing-availability timestamp instead of the period it describes, and a restated value is stored as a new immutable row rather than overwriting the original — so "what did we know on date X" and "what's the latest known value" are two different, both-correct queries.

## SDKs & examples

| | |
|---|---|
| Python SDK | [`sdk/python`](./sdk/python) — [README](./sdk/python/README.md) |
| JavaScript/Node SDK | [`sdk/js`](./sdk/js) — [README](./sdk/js/README.md) |
| Quickstart scripts | [`sdk/examples/python_quickstart.py`](./sdk/examples/python_quickstart.py), [`sdk/examples/js_quickstart.js`](./sdk/examples/js_quickstart.js) |
| OpenAPI spec | https://api.xfinlab.com/api/intelligence/openapi.json |
| Postman collection | https://api.xfinlab.com/api/intelligence/postman.json |

Both SDKs are MIT-licensed ([`sdk/LICENSE`](./sdk/LICENSE)) and have zero required dependencies beyond the standard library / native `fetch`.

## Consumer product

The same backend also powers [xfinlab.com](https://www.xfinlab.com), a retail investment-research platform:

| Module | Path |
|---|---|
| Homepage | `index.html` |
| AI Market Research™ | `ai-analysis.html` |
| Chart Research™ | `chart-analysis.html` |
| Company Compare™ | `company-compare.html` |
| Event Intelligence™ | `news-denoise.html` |
| Risk Engine™ | `stress-lab.html` |

## Local development

```bash
python3 mock-server.py
```

Then open [http://localhost:8080](http://localhost:8080). The production backend is a separate, private service (deployed as `api.xfinlab.com`); the static site above deploys separately on Vercel as `xfinlab.com`.

## More docs

- [XFINLAB_ARCHITECTURE.md](./XFINLAB_ARCHITECTURE.md) — full system architecture
- [PROJECT_ROADMAP.md](./PROJECT_ROADMAP.md) — roadmap
- [PROJECT_STYLE_GUIDE.md](./PROJECT_STYLE_GUIDE.md) — UI style guide
- [DATA-LICENSE-MATRIX.md](./DATA-LICENSE-MATRIX.md) — upstream data source licensing for every paid endpoint
- [MCP_MARKETPLACE_SUBMISSION.md](./MCP_MARKETPLACE_SUBMISSION.md) — MCP server directory submission copy
