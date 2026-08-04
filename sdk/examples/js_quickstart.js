/**
 * Runnable quickstart for the XFINLAB Intelligence API JS/Node client.
 *
 * Usage:
 *   npm install "github:lnanology/Xfinlab#path:sdk/js"
 *   XFINLAB_API_KEY=xfl_... node examples/js_quickstart.js
 *
 * Requires Node 18+ (native fetch). Get a free key (issued instantly):
 * https://www.xfinlab.com/intelligence-api.html
 */
const { XfinlabClient } = require('xfinlab-intelligence');

async function main() {
  const apiKey = process.env.XFINLAB_API_KEY;
  if (!apiKey) {
    console.error('Set XFINLAB_API_KEY in your environment first.');
    console.error('Get a free key: https://www.xfinlab.com/intelligence-api.html');
    process.exit(1);
  }

  const client = new XfinlabClient(apiKey);

  console.log('== /intelligence/status (public, no key needed) ==');
  console.log(await client.status());

  console.log('\n== Recent AAPL headlines ==');
  try {
    const events = await client.events({ ticker: 'AAPL', limit: 5 });
    events.forEach((item) => console.log(`- [${item.source}] ${item.title}`));
  } catch (e) {
    console.error(`events() failed (${e.statusCode}): ${e.message}`);
  }

  console.log('\n== AAPL sentiment (FinBERT) ==');
  try {
    const sentiment = await client.sentiment('AAPL');
    console.log(
      `Average score: ${sentiment.average_score} across ${(sentiment.results || []).length} headlines`
    );
  } catch (e) {
    console.error(`sentiment() failed (${e.statusCode}): ${e.message}`);
  }

  console.log('\n== AAPL technical / market structure ==');
  try {
    const tech = await client.technical('AAPL', { period: '6mo' });
    const confluence = tech.confluence || {};
    console.log(`Confluence: ${confluence.direction} (${confluence.confidence}% confidence)`);
  } catch (e) {
    console.error(`technical() failed (${e.statusCode}): ${e.message}`);
  }
}

main();
