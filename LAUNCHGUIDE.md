# XFINLAB Intelligence

## Tagline
Real-time market news, FinBERT sentiment, technical analysis, and AI-structured event feeds for any ticker — via MCP.

## Description
XFINLAB Intelligence exposes the same data and analysis engines behind XFINLAB's Intelligence API (www.xfinlab.com/intelligence-api.html) as MCP tools, so an AI agent can pull real market data directly instead of a developer hand-writing HTTP client code against the REST API.

Everything returned is real, structured data computed from live sources — deduplicated RSS news aggregation, FinBERT model inference for sentiment (not a fabricated estimate), OHLC-price-derived technical/market-structure signals, and AI-written narrative summaries built from actual headline clusters. Nothing here is a directional trading signal or a probability estimate on future price movement — XFINLAB deliberately stays on the "structured facts and analysis" side of that line, not investment advice.

Built for developers and AI-agent builders who want financial market context in their agent without standing up their own news/data pipeline: research assistants, trading-adjacent copilots, portfolio-review agents, and general-purpose agents that occasionally need "what's going on with this stock."

## Setup Requirements
- `X-API-Key` (required): An XFINLAB Intelligence API key. Get a free one at https://www.xfinlab.com/intelligence-api.html#access — no credit card required for the free tier. Supply it as an HTTP header on the MCP connection (preferred, works with Claude Desktop's custom-header config) or as an `api_key` argument on each tool call for clients that can't set custom headers.
- `X-Marketplace-License-Key` (optional): a license key for this listing's paid tier on mcp-marketplace.io. When present and valid, it upgrades a free-tier XFINLAB key to Pro-tier daily quota (5,000 calls/day) for that call — no separate XFINLAB Pro subscription needed. Supply it as an HTTP header (preferred) or a `marketplace_license_key` tool argument.

## Category
Finance

## Features
- Aggregated real-time market/company news, deduplicated across sources, filterable by ticker
- FinBERT sentiment analysis on recent headlines for any ticker — real model inference with per-headline label, confidence, and score
- Technical/market-structure analysis from live OHLC data: confluence direction, trend, MACD, volume, chart patterns, BOS/CHOCH/liquidity-sweep/order-flow/volume-profile signals
- AI-structured intelligence feed: same-story headline clusters with entity/sentiment/quant-context fields and an AI-written narrative summary — structured fact extraction, never a trading signal
- Cross-region global market map: macro indicators (GDP/inflation/unemployment with source attribution), regional headlines, and sentiment across 10 world regions in one call
- Free tier available (300 calls/day); Pro tier for higher-volume/production use

## Getting Started
- "What's the latest news on NVDA?"
- "What's the sentiment on Tesla headlines right now?"
- "Give me the technical analysis and market structure for AAPL over the last 6 months"
- "Summarize the latest AI-clustered market intelligence feed for the semiconductor sector"
- "Give me a snapshot of what's happening across US, Europe, and Asia markets today"
- Tool: get_market_events — recent deduplicated news headlines, optionally filtered by ticker
- Tool: get_sentiment — FinBERT sentiment analysis of recent headlines for a ticker
- Tool: get_technical_analysis — confluence/trend/MACD/market-structure signals from live OHLC data
- Tool: get_intelligence_feed — AI-structured event clusters with narrative summaries
- Tool: get_global_market_map — cross-region macro + headlines + sentiment snapshot

## Tags
finance, stocks, market-data, sentiment-analysis, technical-analysis, news, trading-research, fintech, real-time-data, finbert

## Documentation URL
https://www.xfinlab.com/intelligence-api.html

## Health Check URL
https://api.xfinlab.com/health
