# XFINLAB Intelligence API v1 — Data License Matrix

**Purpose:** before scaling XFINLAB's Intelligence API into the primary commercial product ("API-first" pivot), this maps every *paid* `/intelligence/v1/*` endpoint to the upstream data source(s) it actually depends on, and that source's real license status.

**Source of truth:** this file does not introduce new judgments about licensing — it rolls up what already exists in `services/license_registry.py` and `services/source_registry.py` (both already in this repo, last updated 2026-08-10) and maps it onto the *specific endpoints being sold*, which neither of those files does directly. If a source's status changes, update `license_registry.py` first; this file should be regenerated from it, not edited independently.

**2026-08-11 update (CONFIRMED):** AJ checked the Railway production dashboard directly — `ALPACA_API_KEY_ID` and `ALPACA_API_SECRET_KEY` are **completely absent**, not just in this repo's local `.env` but in the actual live backend. This means the Alpaca-first routing built into `technical_analysis_service.py` never fires in production today — every request for every symbol, US-listed or not, falls straight through to yfinance. Every row below that was previously "medium–high depending on config" is now confirmed **high**. This is no longer a documentation gap, it's a live production fact: **the paid Intelligence API is currently 100% yfinance-backed for every endpoint that touches price/OHLC data.**

---

## Per-endpoint breakdown

| Endpoint | Weight | Service chain | Upstream source(s) | Worst-case license status | Risk |
|---|---|---|---|---|---|
| `GET /v1/events` | 1x | `rss_news_service` | investing_com_rss (unknown/unverified), globenewswire_rss (public domain), prnewswire_rss (public domain) | unknown (investing.com leg) | medium |
| `GET /v1/sentiment` | 1x | `rss_news_service` (headlines) + `finbert_sentiment_service` | same as above + huggingface_inference_api (commercial) | unknown (investing.com leg only) | medium |
| `GET /v1/debate` | 5x | `agent_debate_service` (+ `technical_analysis_service` for context) | LLM providers (Claude/Groq/DeepSeek/OpenRouter/Kimi — standard paid commercial APIs, not a data-license risk) + Alpaca/yfinance chain for price context | yahoo_finance (confirmed live — Alpaca never fires) | **high** |
| `GET /v1/intel/latest`, `GET /v1/intel/{ticker}` | 8x | `intelligence_pipeline_service` → `news_dedup_engine`, `ai_news_object_service`, `news_impact_engine`, `ai_journalist_service`, `event_chain_service` | rss_news_service pool + `market_data_gateway` → `technical_analysis_service` (Alpaca-first/yfinance-fallback) + finbert + LLM | yahoo_finance (confirmed live — Alpaca never fires) | **highest exposure** — flagship endpoint, 8x weight, touches every upstream category at once |
| `GET /v1/technical/{ticker}` | 3x | `technical_analysis_service` | Alpaca path exists in code but keys are absent in production → **100% yfinance today**, all symbols | yahoo_finance (confirmed live) | **high** |
| `POST /v1/stress-test` | 3x | `monte_carlo_service` → `fetch_ohlc_history` | same — **100% yfinance today**, all symbols | yahoo_finance (confirmed live) | **high** |
| `GET /v1/regime-signal/{ticker}` | 3x | `regime_router_service` → `backtest_service` + `formula_composer_service` → `technical_analysis_service` | same — **100% yfinance today**, all symbols | yahoo_finance (confirmed live) | **high** |
| `GET /v1/world/market-map` | 6x | `world_engine_service` | finbert (huggingface, low) + `global_news_region_service` (rss pool + BBC RSS + gdelt) + `macro_data_service` (World Bank, public domain, low) | **BBC RSS feed is used here but has no entry in `license_registry.py`** — documentation gap, not necessarily a legal problem, but needs one | low, pending the BBC gap being closed |
| `GET /v1/world/regions` | — | `world_engine_service.list_regions` | static, no external call | — | none |

## What this confirms

Every endpoint that touches raw price/OHLC data (`technical`, `stress-test`, `regime-signal`, and the price-context leg of `debate` and `intel/*`) already has the Alpaca-first/yfinance-fallback code path built in `technical_analysis_service.py` (built 2026-07 specifically to reduce yfinance exposure) — but as of 2026-08-11 that code path is dormant in production because no Alpaca credentials are configured. This is a **config gap, not a code gap**: no new engineering is needed, just provisioning real credentials and setting two environment variables in Railway.

`market_data_service.py` (the fully-yfinance, unmitigated `/api/market` and `/api/analyze` consumer endpoints) is confirmed **not** used by any Intelligence API v1 endpoint — its risk is real but belongs to the consumer surface that this pivot is de-emphasizing anyway, not the product being sold.

## Action items, in priority order

1. **Sign up for an Alpaca Markets account (free tier, commercial-use-clean per `license_registry.py`) and set `ALPACA_API_KEY_ID` / `ALPACA_API_SECRET_KEY` in Railway's Variables tab.** This is an account signup + a config change only — no code needs to be written or changed, the routing logic already exists and will start firing the moment the keys are present. This is now the single highest-priority open item in this whole audit; everything else is secondary until this is done.
2. **After the keys are set, spot-check a few `technical`/`stress-test`/`regime-signal` calls for a US ticker (e.g. AAPL) and confirm Alpaca is actually being used**, not just configured — e.g. via logs, since the code silently falls back to yfinance on any Alpaca error and that failure mode should not go unnoticed.
3. **Decide the non-US-symbol gap.** Alpaca only covers US exchanges — every non-US ticker (HK, TW, etc.) served by `technical`, `stress-test`, or `regime-signal` has no Alpaca path even after step 1, and is always yfinance. If non-US tickers are a meaningful share of API demand, this needs either a licensed non-US data source or an explicit scope decision (e.g. "API v1 officially only guarantees data-source cleanliness for US-listed symbols").
4. **Add a BBC RSS entry to `services/license_registry.py`** — small, low-effort documentation gap found during this pass, feeds `world/market-map`.
5. **Verify `investing_com_rss`'s actual redistribution terms**, since it feeds `events`, `sentiment`, and `intel/*` — currently flagged conservatively as "unknown," not confirmed either way.
6. Once 1–3 are resolved, the marketing copy on `intelligence-api.html` and any new "Financial Intelligence Infrastructure" positioning should say plainly which endpoints are commercially clean end-to-end vs. which have a fallback-path caveat — that's a differentiator against competitors who don't disclose this at all, not just a liability shield.

This document does not replace legal review before large-scale commercial launch — it establishes the factual baseline (what actually calls what) so that a lawyer, if/when engaged, is reviewing real usage instead of guesses.
