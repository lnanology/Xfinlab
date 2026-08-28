# XFINLAB

**Financial Intelligence Infrastructure — APIs, SDKs, and an MCP server for developers and AI agents, plus a consumer research platform built on the same backend.**

Real market events, FinBERT sentiment, technical/market-structure analysis, SEC/CFTC/FDIC/USDA/CBOE official data, and Monte Carlo stress testing. Every field is traceable to a real computation or an official data source — nothing fabricated or interpolated.

[Get a free API key](https://www.xfinlab.com/intelligence-api.html) · [API docs](https://www.xfinlab.com/intelligence-api.html) · [llms.txt](https://www.xfinlab.com/llms.txt) · [Consumer product](https://www.xfinlab.com)

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

Server source: [`api/mcp_server.py`](./api/mcp_server.py). Tools: `get_market_events`, `get_sentiment`, `get_technical_analysis`, `get_intelligence_feed`, `get_global_market_map`. Same auth and free tier as the REST API. Docs: [intelligence-api.html#mcp](https://www.xfinlab.com/intelligence-api.html#mcp).

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

Then open [http://localhost:8080](http://localhost:8080). The production backend is a separate FastAPI app (`backend/main.py`, deployed on Railway as `api.xfinlab.com`); the static site above deploys separately on Vercel as `xfinlab.com`.

## More docs

- [XFINLAB_ARCHITECTURE.md](./XFINLAB_ARCHITECTURE.md) — full system architecture
- [PROJECT_ROADMAP.md](./PROJECT_ROADMAP.md) — roadmap
- [PROJECT_STYLE_GUIDE.md](./PROJECT_STYLE_GUIDE.md) — UI style guide
- [DATA-LICENSE-MATRIX.md](./DATA-LICENSE-MATRIX.md) — upstream data source licensing for every paid endpoint
- [MCP_MARKETPLACE_SUBMISSION.md](./MCP_MARKETPLACE_SUBMISSION.md) — MCP server directory submission copy
