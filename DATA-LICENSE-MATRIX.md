# XFINLAB Intelligence API v1 — Data License Matrix

**Purpose:** before scaling XFINLAB's Intelligence API into the primary commercial product ("API-first" pivot), this maps every *paid* `/intelligence/v1/*` endpoint to the upstream data source(s) it actually depends on, and that source's real license status.

**Source of truth:** this file does not introduce new judgments about licensing — it rolls up what already exists in `services/license_registry.py` and `services/source_registry.py` (both already in this repo, last updated 2026-08-10) and maps it onto the *specific endpoints being sold*, which neither of those files does directly. If a source's status changes, update `license_registry.py` first; this file should be regenerated from it, not edited independently.

**2026-08-11 update:** verified `ALPACA_API_KEY_ID` is **not present** in this repo's local `.env` / `.env.local`. This does not prove it's unset in the production (Railway) environment — that must be checked directly in the Railway dashboard, not assumed either way. If it is unset in production, every endpoint below marked "Alpaca-first" is silently running 100% on the yfinance fallback path today, which changes several rows from *medium* to *high* priority. **This is the single highest-value thing to check next — takes 2 minutes, resolves the biggest unknown in this whole document.**

---

## Per-endpoint breakdown

| Endpoint | Weight | Service chain | Upstream source(s) | Worst-case license status | Risk |
|---|---|---|---|---|---|
| `GET /v1/events` | 1x | `rss_news_service` | investing_com_rss (unknown/unverified), globenewswire_rss (public domain), prnewswire_rss (public domain) | unknown (investing.com leg) | medium |
| `GET /v1/sentiment` | 1x | `rss_news_service` (headlines) + `finbert_sentiment_service` | same as above + huggingface_inference_api (commercial) | unknown (investing.com leg only) | medium |
| `GET /v1/debate` | 5x | `agent_debate_service` (+ `technical_analysis_service` for context) | LLM providers (Claude/Groq/DeepSeek/OpenRouter/Kimi — standard paid commercial APIs, not a data-license risk) + Alpaca/yfinance chain for price context | yahoo_finance (fallback leg) | medium |
| `GET /v1/intel/latest`, `GET /v1/intel/{ticker}` | 8x | `intelligence_pipeline_service` → `news_dedup_engine`, `ai_news_object_service`, `news_impact_engine`, `ai_journalist_service`, `event_chain_service` | rss_news_service pool + `market_data_gateway` → `technical_analysis_service` (Alpaca-first/yfinance-fallback) + finbert + LLM | yahoo_finance (fallback leg) | **highest exposure** — flagship endpoint touches every upstream category at once |
| `GET /v1/technical/{ticker}` | 3x | `technical_analysis_service` | Alpaca (US symbols, if keys configured) → yfinance (non-US symbols, or Alpaca not configured/errors) | yahoo_finance (fallback leg) | medium–high depending on Alpaca config status |
| `POST /v1/stress-test` | 3x | `monte_carlo_service` → `fetch_ohlc_history` | same Alpaca-first/yfinance-fallback chain as `technical_analysis_service` | yahoo_finance (fallback leg) | medium–high depending on Alpaca config status |
| `GET /v1/regime-signal/{ticker}` | 3x | `regime_router_service` → `backtest_service` + `formula_composer_service` → `technical_analysis_service` | same chain | yahoo_finance (fallback leg) | medium–high depending on Alpaca config status |
| `GET /v1/world/market-map` | 6x | `world_engine_service` | finbert (huggingface, low) + `global_news_region_service` (rss pool + BBC RSS + gdelt) + `macro_data_service` (World Bank, public domain, low) | **BBC RSS feed is used here but has no entry in `license_registry.py`** — documentation gap, not necessarily a legal problem, but needs one | low, pending the BBC gap being closed |
| `GET /v1/world/regions` | — | `world_engine_service.list_regions` | static, no external call | — | none |

## What this confirms

Every endpoint that touches raw price/OHLC data (`technical`, `stress-test`, `regime-signal`, and the price-context leg of `debate` and `intel/*`) already routes through the same Alpaca-first/yfinance-fallback chain in `technical_analysis_service.py` — this was already built (2026-07) specifically to reduce yfinance exposure, it is not something that needs building. The remaining exposure is real but bounded to two cases: (1) non-US-listed symbols, which have no Alpaca path at all and always use yfinance, and (2) whatever fraction of US-symbol requests hit yfinance because Alpaca keys are missing or a request errors.

`market_data_service.py` (the fully-yfinance, unmitigated `/api/market` and `/api/analyze` consumer endpoints) is confirmed **not** used by any Intelligence API v1 endpoint — its risk is real but belongs to the consumer surface that this pivot is de-emphasizing anyway, not the product being sold.

## Action items, in priority order

1. **Confirm `ALPACA_API_KEY_ID`/`ALPACA_API_SECRET_KEY` are actually set in the production Railway environment** — 2 minutes, resolves whether the "medium" risk rows above are actually "low" (Alpaca genuinely serving most US-symbol traffic) or actually "high" (silently 100% yfinance). Do this before anything else below.
2. **Decide the non-US-symbol gap.** Alpaca only covers US exchanges — every non-US ticker (HK, TW, etc.) served by `technical`, `stress-test`, or `regime-signal` has no Alpaca path and is always yfinance today. If non-US tickers are a meaningful share of API demand, this needs either a licensed non-US data source or an explicit scope decision (e.g. "API v1 officially only guarantees data-source cleanliness for US-listed symbols").
3. **Add a BBC RSS entry to `services/license_registry.py`** — small, low-effort documentation gap found during this pass, feeds `world/market-map`.
4. **Verify `investing_com_rss`'s actual redistribution terms**, since it feeds `events`, `sentiment`, and `intel/*` — currently flagged conservatively as "unknown," not confirmed either way.
5. Once 1–2 are resolved, the marketing copy on `intelligence-api.html` and any new "Financial Intelligence Infrastructure" positioning should say plainly which endpoints are commercially clean end-to-end vs. which have a fallback-path caveat — that's a differentiator against competitors who don't disclose this at all, not just a liability shield.

This document does not replace legal review before large-scale commercial launch — it establishes the factual baseline (what actually calls what) so that a lawyer, if/when engaged, is reviewing real usage instead of guesses.
