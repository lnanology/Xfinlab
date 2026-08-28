/**
 * XFINLAB Intelligence API -- official JavaScript/Node client.
 *
 * Wraps https://api.xfinlab.com's Intelligence API v1 (see api/intelligence.py
 * in the main XFINLAB repo for the server-side implementation this mirrors).
 * Zero dependencies -- uses the global `fetch` (available natively in
 * browsers and Node 18+; for older Node, install a fetch polyfill such as
 * `node-fetch` and set it as `globalThis.fetch` before constructing a
 * client). UMD wrapper: works via `require()` in Node, a `<script>` tag in
 * the browser (exposes `window.Xfinlab`), or an ES module bundler.
 *
 * Not yet published to npm -- there are no paying developers on this API
 * yet to justify the maintenance overhead of a public package release
 * (same honest, no-premature-infrastructure posture as the rest of this
 * codebase). Install straight from the repo in the meantime:
 *
 *   npm install "github:lnanology/Xfinlab#path:sdk/js"
 *
 * or copy this single file into your own project -- it has no internal
 * imports, so vendoring it works too.
 *
 * Get a free API key (issued instantly): https://www.xfinlab.com/intelligence-api.html
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) {
    module.exports = factory();
  } else {
    root.Xfinlab = factory();
  }
}(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  function XfinlabError(message, statusCode) {
    this.name = 'XfinlabError';
    this.message = message;
    this.statusCode = statusCode;
  }
  XfinlabError.prototype = Object.create(Error.prototype);
  XfinlabError.prototype.constructor = XfinlabError;

  /**
   * @param {string} apiKey
   * @param {{baseUrl?: string, timeoutMs?: number}} [options]
   */
  function XfinlabClient(apiKey, options) {
    if (!apiKey) {
      throw new Error(
        'apiKey is required -- get a free key at https://www.xfinlab.com/intelligence-api.html'
      );
    }
    options = options || {};
    this.apiKey = apiKey;
    this.baseUrl = (options.baseUrl || 'https://api.xfinlab.com/api').replace(/\/+$/, '');
    this.timeoutMs = options.timeoutMs || 30000;
  }

  // -- internals ---------------------------------------------------------

  XfinlabClient.prototype._buildUrl = function (path, params) {
    var url = this.baseUrl + path;
    var pairs = [];
    if (params) {
      Object.keys(params).forEach(function (k) {
        var v = params[k];
        if (v !== undefined && v !== null) {
          pairs.push(encodeURIComponent(k) + '=' + encodeURIComponent(v));
        }
      });
    }
    return pairs.length ? url + '?' + pairs.join('&') : url;
  };

  XfinlabClient.prototype._request = function (method, path, params, jsonBody) {
    var self = this;
    var url = self._buildUrl(path, params);
    var hasAbort = typeof AbortController !== 'undefined';
    var controller = hasAbort ? new AbortController() : null;
    var timer = controller
      ? setTimeout(function () { controller.abort(); }, self.timeoutMs)
      : null;

    var fetchOpts = {
      method: method,
      headers: { 'X-API-Key': self.apiKey },
    };
    if (controller) fetchOpts.signal = controller.signal;
    if (jsonBody !== undefined && jsonBody !== null) {
      fetchOpts.headers['Content-Type'] = 'application/json';
      fetchOpts.body = JSON.stringify(jsonBody);
    }

    return fetch(url, fetchOpts).then(function (resp) {
      if (timer) clearTimeout(timer);
      return resp.json().catch(function () {
        throw new XfinlabError('Non-JSON response (' + resp.status + ')', resp.status);
      }).then(function (body) {
        if (!resp.ok || (body && body.success === false)) {
          var msg = (body && (body.detail || body.error)) || ('Request failed (' + resp.status + ')');
          throw new XfinlabError(msg, resp.status);
        }
        return (body && typeof body === 'object' && 'data' in body) ? body.data : body;
      });
    });
  };

  XfinlabClient.prototype._get = function (path, params) {
    return this._request('GET', path, params);
  };

  XfinlabClient.prototype._post = function (path, jsonBody) {
    return this._request('POST', path, null, jsonBody);
  };

  // -- public, unauthenticated --------------------------------------------

  XfinlabClient.prototype.status = function () {
    return this._get('/intelligence/status');
  };

  // -- v1 endpoints (require an API key) -----------------------------------

  XfinlabClient.prototype.events = function (opts) {
    opts = opts || {};
    return this._get('/intelligence/v1/events', { ticker: opts.ticker, limit: opts.limit || 20 });
  };

  XfinlabClient.prototype.sentiment = function (ticker, limit) {
    return this._get('/intelligence/v1/sentiment', { ticker: ticker, limit: limit || 10 });
  };

  // Most expensive endpoint (4 sequential LLM calls server-side, weighted
  // 5x in your daily quota) -- see intelligence-api.html for the full
  // cost-weighting table.
  XfinlabClient.prototype.debate = function (ticker) {
    return this._get('/intelligence/v1/debate', { ticker: ticker });
  };

  XfinlabClient.prototype.intelLatest = function (opts) {
    opts = opts || {};
    return this._get('/intelligence/v1/intel/latest', {
      limit: opts.limit || 5,
      lang: opts.lang || 'zh-HK',
    });
  };

  XfinlabClient.prototype.intelForTicker = function (ticker, opts) {
    opts = opts || {};
    return this._get('/intelligence/v1/intel/' + encodeURIComponent(ticker), {
      limit: opts.limit || 5,
      lang: opts.lang || 'zh-HK',
    });
  };

  XfinlabClient.prototype.technical = function (ticker, opts) {
    opts = opts || {};
    return this._get('/intelligence/v1/technical/' + encodeURIComponent(ticker), {
      period: opts.period || '6mo',
      interval: opts.interval || '1d',
      lang: opts.lang || 'en',
    });
  };

  XfinlabClient.prototype.stressTest = function (params) {
    return this._post('/intelligence/v1/stress-test', params);
  };

  // 2026-08-27: this SDK had fallen behind the live API by 6 endpoints --
  // regimeSignal/forecast (shipped 2026-08-10/08-24) were never wrapped,
  // and this batch adds the 4 newest (Data Factory -> Intelligence API
  // monetization: insider/shortInterest/energy/exchange).

  XfinlabClient.prototype.regimeSignal = function (ticker, opts) {
    opts = opts || {};
    return this._get('/intelligence/v1/regime-signal/' + encodeURIComponent(ticker), {
      regime: opts.regime,
      min_trades: opts.minTrades,
    });
  };

  XfinlabClient.prototype.forecast = function (ticker, opts) {
    opts = opts || {};
    return this._get('/intelligence/v1/forecast/' + encodeURIComponent(ticker), {
      horizon_days: opts.horizonDays,
      n_simulations: opts.nSimulations,
    });
  };

  XfinlabClient.prototype.insider = function (ticker) {
    return this._get('/intelligence/v1/insider/' + encodeURIComponent(ticker));
  };

  XfinlabClient.prototype.shortInterest = function (ticker) {
    return this._get('/intelligence/v1/short-interest/' + encodeURIComponent(ticker));
  };

  XfinlabClient.prototype.energy = function (ticker) {
    return this._get('/intelligence/v1/energy/' + encodeURIComponent(ticker));
  };

  XfinlabClient.prototype.exchange = function (ticker) {
    return this._get('/intelligence/v1/exchange/' + encodeURIComponent(ticker));
  };

  // 2026-08-28: fundamentals/vixTermStructure/bankHealth/agriculture --
  // same Data Factory monetization batch as the Python SDK's update.
  XfinlabClient.prototype.fundamentals = function (ticker) {
    return this._get('/intelligence/v1/fundamentals/' + encodeURIComponent(ticker));
  };

  XfinlabClient.prototype.vixTermStructure = function () {
    return this._get('/intelligence/v1/vix-term-structure');
  };

  XfinlabClient.prototype.bankHealth = function (ticker) {
    return this._get('/intelligence/v1/bank-health/' + encodeURIComponent(ticker));
  };

  XfinlabClient.prototype.agriculture = function (ticker) {
    return this._get('/intelligence/v1/agriculture/' + encodeURIComponent(ticker));
  };

  return { XfinlabClient: XfinlabClient, XfinlabError: XfinlabError };
}));
