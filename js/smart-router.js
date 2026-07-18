// XFINLAB Smart AI Router -- powers the homepage's single "tell me
// what you're thinking" input box. Given whatever free text a visitor
// types (a bare ticker, "AAPL 走勢圖", "比較 TSLA 同 FORD", "邊隻股份
// 值博率最高" etc), figures out which of the 11 Engine pages best
// answers it and navigates there with the ticker/question prefilled.
//
// Mirrors services/intent_router_service.py's two-stage design:
//   1. Fast, free, instant regex/keyword pass done entirely client-side.
//   2. If that's inconclusive, calls GET /api/smart-route which re-runs
//      the same fast pass server-side and falls back to an AI
//      classification call only as a last resort.
// A bare ticker with no other intent keyword resolves to "analysis" --
// meaning "stay on the homepage", since the existing inline demo card
// (index.html's runDemo()) already handles that case perfectly.
(function () {
  var INTENT_MAP = {
    chart:       { page: 'chart-analysis.html',  param: 'symbol' },
    compare:     { page: 'company-compare.html', param: 'companies' },
    probability: { page: 'probability-scan.html',param: 'ticker' },
    anomaly:     { page: 'anomaly.html',         param: 'ticker' },
    portfolio:   { page: 'portfolio.html',       param: null },
    news:        { page: 'news-denoise.html',    param: 'query' },
    stress:      { page: 'stress-lab.html',      param: null },
    screener:    { page: 'screener.html',        param: null },
    chat:        { page: 'chat.html',            param: 'q' },
    dashboard:   { page: 'dashboard.html',       param: null },
    analysis:    { page: null,                   param: null }
  };

  var KEYWORDS = [
    ['compare', ['比較', '對比', '同邊隻好', 'vs', 'compare', 'which is better']],
    ['chart', ['圖表', 'k線', 'k线', '型態', '走勢圖', 'chart', 'candlestick', 'pattern']],
    ['anomaly', ['異常', '暴增', '爆量', '反常', 'volume spike', 'anomaly', 'unusual volume']],
    ['probability', ['機率', '概率', '會唔會升', '會唔會跌', 'bullish', 'bearish', 'probability', '會升定跌']],
    ['portfolio', ['配置', '持倉', 'portfolio', 'allocation', '分散投資']],
    ['stress', ['壓力測試', '黑天鵝', 'stress test', '崩盤', 'crash scenario']],
    ['screener', ['篩選', '選股', 'screener', 'screen for', 'find stocks']],
    ['news', ['新聞', '消息', 'news', 'sentiment']],
    ['dashboard', ['自選股', 'watchlist', 'dashboard']]
  ];

  var SYMBOL_RE = /^[A-Za-z0-9.\-=]{1,12}$/;

  function extractTicker(text) {
    var tokens = text.match(/[A-Za-z0-9.\-]{1,12}/g) || [];
    for (var i = 0; i < tokens.length; i++) {
      var candidate = tokens[i].toUpperCase().replace(/^[.\-]+|[.\-]+$/g, '');
      if (!candidate || !SYMBOL_RE.test(candidate)) continue;
      if (/^[A-Z]{1,2}$/.test(candidate)) continue; // skip "vs", "the", etc.
      return candidate;
    }
    return null;
  }

  function classifyFast(query) {
    var q = (query || '').trim();
    if (!q) return null;
    var ticker = extractTicker(q);
    var lower = q.toLowerCase();

    for (var i = 0; i < KEYWORDS.length; i++) {
      var intent = KEYWORDS[i][0];
      var kws = KEYWORDS[i][1];
      for (var j = 0; j < kws.length; j++) {
        if (q.indexOf(kws[j]) !== -1 || lower.indexOf(kws[j]) !== -1) {
          return { intent: intent, ticker: ticker };
        }
      }
    }

    var stripped = q.replace(/[^A-Za-z0-9.\-]/g, '').toUpperCase();
    if (ticker && stripped === ticker) {
      return { intent: 'analysis', ticker: ticker };
    }
    return null;
  }

  function buildUrl(intent, ticker, originalQuery) {
    var meta = INTENT_MAP[intent] || INTENT_MAP.chat;
    if (!meta.page) return null;
    var url = meta.page;
    if (meta.param === 'q') {
      url += '?q=' + encodeURIComponent(originalQuery);
    } else if (meta.param && ticker) {
      url += '?' + meta.param + '=' + encodeURIComponent(ticker);
    }
    return url;
  }

  // Public API: XFLSmartRouter.route(query) -> Promise<{intent, ticker, stayOnHomepage, url}>
  window.XFLSmartRouter = {
    route: function (query) {
      var fast = classifyFast(query);
      if (fast) {
        return Promise.resolve({
          intent: fast.intent,
          ticker: fast.ticker,
          stayOnHomepage: fast.intent === 'analysis',
          url: buildUrl(fast.intent, fast.ticker, query)
        });
      }

      var API = (typeof window.API === 'string' && window.API) || 'https://api.xfinlab.com/api';
      return fetch(API + '/smart-route?q=' + encodeURIComponent(query))
        .then(function (res) { return res.json(); })
        .then(function (data) {
          if (data.status !== 'ok') {
            // Fail safe: treat as a plain ticker/analysis attempt so the
            // homepage's own inline demo card still gets a shot at it.
            return { intent: 'analysis', ticker: extractTicker(query), stayOnHomepage: true, url: null };
          }
          return {
            intent: data.intent,
            ticker: data.ticker,
            stayOnHomepage: !!data.stay_on_homepage,
            url: data.url
          };
        })
        .catch(function () {
          return { intent: 'analysis', ticker: extractTicker(query), stayOnHomepage: true, url: null };
        });
    }
  };
})();
