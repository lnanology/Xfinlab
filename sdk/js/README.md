# xfinlab-intelligence (JavaScript / Node)

Official JavaScript client for the [XFINLAB Intelligence API](https://www.xfinlab.com/intelligence-api.html) -- structured market events, FinBERT sentiment, multi-agent AI debate, an AI-clustered intelligence feed, technical/market-structure analysis, and Monte Carlo stress testing.

Zero dependencies -- uses the native `fetch` (Node 18+, or any modern browser). Not yet published to npm (no paying developers on the API yet to justify maintaining a public package release). Install directly from the repo instead:

```bash
npm install "github:lnanology/Xfinlab#path:sdk/js"
```

Or just copy `xfinlab.js` into your own project / drop it in a `<script>` tag -- it has no internal imports and works as a UMD module (Node `require()`, browser global `window.Xfinlab`, or an ES module bundler).

## Get a key

Free tier keys are issued instantly, no waiting: https://www.xfinlab.com/intelligence-api.html

## Quickstart (Node)

```js
const { XfinlabClient } = require('xfinlab-intelligence');

const client = new XfinlabClient('xfl_...');

const events = await client.events({ ticker: 'AAPL', limit: 10 });
const sentiment = await client.sentiment('AAPL');
const technical = await client.technical('AAPL', { period: '6mo' });
const stress = await client.stressTest({ symbol: 'AAPL', amount: 10000, horizon_days: 252 });

// Pro/Enterprise only:
const debate = await client.debate('AAPL');
const feed = await client.intelForTicker('AAPL', { limit: 5 });
```

## Quickstart (browser)

```html
<script src="xfinlab.js"></script>
<script>
  const client = new Xfinlab.XfinlabClient('xfl_...');
  client.sentiment('AAPL').then(console.log);
</script>
```

Note: don't ship a Pro/Enterprise-tier key in client-side browser code that anyone can view-source -- call these endpoints from your own backend for anything beyond quick local testing.

## Error handling

Every method rejects with an `XfinlabError` (with a `.statusCode` property) on a non-2xx response or an explicit `{"success": false}` from the API -- including `429` when you've hit your daily quota.

```js
try {
  const result = await client.debate('AAPL');
} catch (e) {
  console.error(`Request failed (${e.statusCode}): ${e.message}`);
}
```

## API reference

| Method | Endpoint | Notes |
|---|---|---|
| `status()` | `GET /intelligence/status` | Public, no key required |
| `events({ticker, limit=20})` | `GET /v1/events` | |
| `sentiment(ticker, limit=10)` | `GET /v1/sentiment` | |
| `debate(ticker)` | `GET /v1/debate` | Weighted 5x in quota |
| `intelLatest({limit=5, lang="zh-HK"})` | `GET /v1/intel/latest` | Weighted 8x in quota |
| `intelForTicker(ticker, {limit=5, lang="zh-HK"})` | `GET /v1/intel/{ticker}` | Weighted 8x in quota |
| `technical(ticker, {period="6mo", interval="1d", lang="en"})` | `GET /v1/technical/{ticker}` | Weighted 3x in quota |
| `stressTest({symbol, amount, horizon_days=252, n_simulations, lang})` | `POST /v1/stress-test` | Weighted 3x in quota |
| `regimeSignal(ticker, {regime, minTrades=5})` | `GET /v1/regime-signal/{ticker}` | Weighted 3x in quota |
| `forecast(ticker, {horizonDays=5, nSimulations})` | `GET /v1/forecast/{ticker}` | Weighted 4x in quota |
| `insider(ticker)` | `GET /v1/insider/{ticker}` | Weighted 3x in quota |
| `shortInterest(ticker)` | `GET /v1/short-interest/{ticker}` | Weighted 2x in quota |
| `energy(ticker)` | `GET /v1/energy/{ticker}` | Weighted 2x in quota |
| `exchange(ticker)` | `GET /v1/exchange/{ticker}` | Weighted 2x in quota |
| `fundamentals(ticker)` | `GET /v1/fundamentals/{ticker}` | Weighted 3x in quota |
| `vixTermStructure()` | `GET /v1/vix-term-structure` | Weighted 1x in quota |
| `bankHealth(ticker)` | `GET /v1/bank-health/{ticker}` | Weighted 2x in quota |
| `agriculture(ticker)` | `GET /v1/agriculture/{ticker}` | Weighted 2x in quota |
| `subscribeWebhook(eventType, url, ticker)` | `POST /v1/webhooks/subscribe` | Pro-tier only, no quota spend |
| `listWebhooks()` | `GET /v1/webhooks` | No quota spend |
| `deleteWebhook(webhookId)` | `DELETE /v1/webhooks/{id}` | No quota spend |

Full endpoint docs, pricing tiers, and quota weighting: https://www.xfinlab.com/intelligence-api.html

## License

MIT -- see `../LICENSE`.
