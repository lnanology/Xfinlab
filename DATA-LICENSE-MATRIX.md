# XFINLAB Intelligence API v1 — Data License Matrix

**Purpose:** before scaling XFINLAB's Intelligence API into the primary commercial product ("API-first" pivot), this maps every *paid* `/intelligence/v1/*` endpoint to the upstream data source(s) it actually depends on, and that source's real license status.

**Source of truth:** this file does not introduce new judgments about licensing — it rolls up what already exists in `services/license_registry.py` and `services/source_registry.py` (both already in this repo, last updated 2026-08-10) and maps it onto the *specific endpoints being sold*, which neither of those files does directly. If a source's status changes, update `license_registry.py` first; this file should be regenerated from it, not edited independently.

**2026-08-11 update (RESOLVED):** `ALPACA_API_KEY_ID` / `ALPACA_API_SECRET_KEY` were absent from production, confirmed live via Railway logs showing every price/OHLC-touching endpoint 100% yfinance-backed. AJ has since signed up for Alpaca and set both keys in Railway's Variables tab. Verification along the way surfaced a second, unrelated bug: this app never called `logging.basicConfig()` anywhere, so every `logger.info()` call across the whole codebase (not just this diagnostic) was silently swallowed by Python's default WARNING-only last-resort handler — uvicorn's own access-log lines were unaffected (uvicorn configures its own loggers independently), which made the app look like it was logging normally while it wasn't. Fixed in `backend/main.py` (commit `50b0d67`). With that fixed, production logs now confirm: **`Alpaca served OHLC for AAPL (6mo, 1d)`** — Alpaca is live and serving US-symbol requests as of 2026-08-11. Every row below marked "confirmed live (Alpaca never fires)" is now stale and superseded — see the per-endpoint table for the corrected status.

---

## Per-endpoint breakdown

| Endpoint | Weight | Service chain | Upstream source(s) | Worst-case license status | Risk |
|---|---|---|---|---|---|
| `GET /v1/events` | 1x | `rss_news_service` | investing_com_rss (unknown/unverified), globenewswire_rss (public domain), prnewswire_rss (public domain) | unknown (investing.com leg) | medium |
| `GET /v1/sentiment` | 1x | `rss_news_service` (headlines) + `finbert_sentiment_service` | same as above + huggingface_inference_api (commercial) | unknown (investing.com leg only) | medium |
| `GET /v1/debate` | 5x | `agent_debate_service` (+ `technical_analysis_service` for context) | LLM providers (Claude/Groq/DeepSeek/OpenRouter/Kimi — standard paid commercial APIs, not a data-license risk) + Alpaca/yfinance chain for price context | alpaca_markets for US symbols (confirmed live 2026-08-11), yahoo_finance fallback for non-US or on Alpaca error | low–medium (US symbols), high (non-US symbols) |
| `GET /v1/intel/latest`, `GET /v1/intel/{ticker}` | 8x | `intelligence_pipeline_service` → `news_dedup_engine`, `ai_news_object_service`, `news_impact_engine`, `ai_journalist_service`, `event_chain_service` | rss_news_service pool + `market_data_gateway` → `technical_analysis_service` (Alpaca-first, confirmed live) + finbert + LLM | alpaca_markets for US symbols, yahoo_finance fallback for non-US | low–medium (US symbols), high (non-US symbols) — flagship endpoint, 8x weight |
| `GET /v1/technical/{ticker}` | 3x | `technical_analysis_service` | Alpaca confirmed live in production 2026-08-11 (`Alpaca served OHLC for AAPL (6mo, 1d)` in Railway logs) for US symbols → yfinance fallback for non-US symbols or on Alpaca error | alpaca_markets (US, confirmed), yahoo_finance (non-US) | low–medium (US symbols), high (non-US symbols) |
| `POST /v1/stress-test` | 3x | `monte_carlo_service` → `fetch_ohlc_history` | same — Alpaca-first confirmed live for US symbols | alpaca_markets (US, confirmed), yahoo_finance (non-US) | low–medium (US symbols), high (non-US symbols) |
| `GET /v1/regime-signal/{ticker}` | 3x | `regime_router_service` → `backtest_service` + `formula_composer_service` → `technical_analysis_service` | same — Alpaca-first confirmed live for US symbols | alpaca_markets (US, confirmed), yahoo_finance (non-US) | low–medium (US symbols), high (non-US symbols) |
| `GET /v1/world/market-map` | 6x | `world_engine_service` | finbert (huggingface, low) + `global_news_region_service` (rss pool + BBC RSS + gdelt) + `macro_data_service` (World Bank, public domain, low) | **BBC RSS feed is used here but has no entry in `license_registry.py`** — documentation gap, not necessarily a legal problem, but needs one | low, pending the BBC gap being closed |
| `GET /v1/world/regions` | — | `world_engine_service.list_regions` | static, no external call | — | none |

## What this confirms

Every endpoint that touches raw price/OHLC data (`technical`, `stress-test`, `regime-signal`, and the price-context leg of `debate` and `intel/*`) now actually uses Alpaca (confirmed live via production logs, 2026-08-11) for US-listed symbols. The remaining exposure is now narrowed to exactly one case: **non-US-listed symbols** (HK, TW, etc.), which have no Alpaca path in the code at all and always use yfinance — see action item #1 below.

`market_data_service.py` (the fully-yfinance, unmitigated `/api/market` and `/api/analyze` consumer endpoints) is confirmed **not** used by any Intelligence API v1 endpoint — its risk is real but belongs to the consumer surface that this pivot is de-emphasizing anyway, not the product being sold.

## Action items, in priority order

~~1. Sign up for Alpaca, set `ALPACA_API_KEY_ID`/`ALPACA_API_SECRET_KEY` in Railway.~~ **Done 2026-08-11**, confirmed live via production logs.
~~2. Spot-check that Alpaca is actually being used, not just configured.~~ **Done 2026-08-11** — confirmed via `Alpaca served OHLC for AAPL (6mo, 1d)` in Railway logs. (Along the way this surfaced and fixed an unrelated bug: the app never called `logging.basicConfig()`, so all `.info()`-level logs anywhere in the codebase were silently invisible — see `backend/main.py` commit `50b0d67`. Ongoing monitoring for silent Alpaca-to-yfinance fallback is now actually possible, which it wasn't before.)

1. **Decide the non-US-symbol gap.** Alpaca only covers US exchanges — every non-US ticker (HK, TW, etc.) served by `technical`, `stress-test`, or `regime-signal` has no Alpaca path and is always yfinance. If non-US tickers are a meaningful share of API demand, this needs either a licensed non-US data source or an explicit scope decision (e.g. "API v1 officially only guarantees data-source cleanliness for US-listed symbols").
2. **Add a BBC RSS entry to `services/license_registry.py`** — small, low-effort documentation gap found during this pass, feeds `world/market-map`.
3. **Verify `investing_com_rss`'s actual redistribution terms**, since it feeds `events`, `sentiment`, and `intel/*` — currently flagged conservatively as "unknown," not confirmed either way.
4. Now that the biggest single risk is resolved for US symbols, the marketing copy on `intelligence-api.html` and any new "Financial Intelligence Infrastructure" positioning should say plainly which endpoints are commercially clean end-to-end (US symbols) vs. which still have a yfinance-fallback caveat (non-US symbols) — that's a differentiator against competitors who don't disclose this at all, not just a liability shield.

This document does not replace legal review before large-scale commercial launch — it establishes the factual baseline (what actually calls what) so that a lawyer, if/when engaged, is reviewing real usage instead of guesses.
