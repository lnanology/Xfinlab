# XFINLAB Intelligence MCP Server — marketplace submission copy

Ready-to-paste fields for submitting to mcp.so, Smithery, and PulseMCP. The
server itself lives at [`api/mcp_server.py`](api/mcp_server.py) and has been
live in production since an earlier session; this file exists only to make
submitting it to third-party directories fast. Submission forms require
AJ's own account on each site, so this is copy to paste in, not something
that can be automated end-to-end.

---

## Core facts (same across every listing)

| Field | Value |
|---|---|
| Name | XFINLAB Intelligence |
| Server URL | `https://api.xfinlab.com/api/mcp` |
| Transport | Streamable HTTP (stateless JSON-RPC 2.0 POST; no SSE, no session state) |
| Auth | `X-API-Key` header, or `api_key` argument on each tool call |
| Get a key | https://www.xfinlab.com/intelligence-api.html (free tier, issued instantly) |
| Docs | https://www.xfinlab.com/intelligence-api.html#mcp |
| Repo | https://github.com/lnanology/Xfinlab (server: `api/mcp_server.py`) |
| Category | Finance / Data & APIs |
| License | Server code is part of the main XFINLAB repo; the two companion SDKs (`sdk/python`, `sdk/js`) are MIT |
| Icon | https://www.xfinlab.com/img/logo-mark.png |

## One-liner

Real-time market events, FinBERT sentiment, technical/market-structure analysis, and AI-structured intelligence — as MCP tools, backed by real data with no fabricated numbers.

## Short description (2-3 sentences)

XFINLAB Intelligence exposes five MCP tools over market events, sentiment, technical analysis, AI-clustered news intelligence, and a global cross-region market map. Every number is traceable to a real computation — the AI Intelligence Feed tool never returns a directional trading signal or probability estimate. Free tier API keys are issued instantly and automatically at intelligence-api.html.

## Tools

1. **`get_market_events`** — recent market/company headlines, optionally filtered by ticker.
2. **`get_sentiment`** — FinBERT-scored sentiment across a ticker's recent headlines.
3. **`get_technical_analysis`** — confluence direction/confidence, trend, MACD, volume, chart patterns, and market structure (BOS/CHOCH, liquidity sweeps, order flow, volume profile, institutional footprint) from real OHLC data.
4. **`get_intelligence_feed`** — same-event headlines clustered, enriched with entities/sentiment/technical signals, and an AI-written narrative summary.
5. **`get_global_market_map`** — cross-region macro + news + sentiment snapshot across 10 regions (US, Europe, Japan, Korea, China, HK, Taiwan, SE Asia, Middle East, LatAm).

## Connection config (Claude Desktop / any remote-HTTP-capable MCP client)

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

---

## mcp.so submission notes

mcp.so mostly crawls a GitHub repo + README for its listing. Point it at
`https://github.com/lnanology/Xfinlab` with subdirectory context
`api/mcp_server.py`, or use their manual "Submit a server" form with the
Core facts table above. **Before submitting: confirm the GitHub repo is
public** — mcp.so can't index a private repo, and this hasn't been
independently verified from inside this session (`git remote -v` shows a
token-authenticated push URL, which happens for both public and private
repos, so it isn't proof either way).

## Smithery submission notes

Smithery does editorial review and supports hosted install/auth flows.
Their form typically asks for: server name, one-liner, category, transport
type (select "Streamable HTTP" / "Remote HTTP", not stdio), the server URL,
and an auth description — use the Core facts + auth row above. Mention the
free-tier self-serve key issuance explicitly; Smithery's reviewers favor
servers a user can actually try without an approval wait.

## PulseMCP submission notes

PulseMCP is directory + editorial news — good for a launch-day post in
addition to the listing itself. Use the short description above as the
listing body, and consider a short "why we built this" blurb for their news
angle: XFINLAB already ships a consumer research product on real,
commercially-licensed data (see the Data Sourcing section of
intelligence-api.html); this MCP server exposes the same backend to AI
agents directly, rather than requiring an agent to scrape the UI.
