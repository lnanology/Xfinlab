/*
 * Shared TradingView Advanced Chart embed helper.
 *
 * Uses TradingView's official free "Advanced Chart" embed (embed-widget-
 * advanced-chart.js) -- no API key, no login, no server-side integration
 * needed. This is separate from and additional to each page's own real-
 * data lightweight-charts candlestick chart (which drives the actual
 * Support/Resistance/RSI/MACD/Decision Levels numbers) -- TradingView is
 * shown purely as a familiar, professional-grade visual reference
 * alongside it.
 *
 * Because the widget's config is parsed once at DOM-insertion time (it's
 * a <script> tag with an inline JSON body, TradingView's own embed
 * convention), changing the symbol requires tearing down and rebuilding
 * the whole widget node -- innerHTML replacement won't re-execute the
 * <script>, so this always uses real createElement/appendChild.
 *
 * Usage: window.renderTradingViewWidget(containerId, symbol)
 *   symbol = whatever normalizeGlobalTicker() already produced on the
 *   calling page (e.g. 'AAPL', '0700.HK', 'BTC-USD', 'ES=F').
 */
(function () {
  // Best-effort mapping from XFINLAB's internal ticker format (Yahoo-style
  // suffixes, since that's what services/ticker_search_service.py's global
  // search + normalizeGlobalTicker() already produce) to TradingView's
  // EXCHANGE:SYMBOL format.
  //
  // 2026-07-20: expanded on a real bug report -- "某D股票 TradingView 顯示不到"
  // (TradingView won't show for certain stocks). Root cause: the live
  // global-asset search (services/ticker_search_service.py, via yfinance's
  // Lookup) can return real, analyzable tickers from many more exchanges
  // than the 6 suffixes this map originally covered -- e.g. Australian
  // (.AX), Indian (.NS/.BO), German (.DE), French/Dutch/Belgian/
  // Portuguese (.PA/.AS/.BR/.LS, all Euronext), Brazilian (.SA), Canadian
  // (.TO), Singaporean (.SI) -- so those were falling into the generic
  // "anything else unmapped" bucket and showing "not supported" even
  // though TradingView genuinely does have charts for them, just under a
  // different exchange prefix. Every mapping added below was verified
  // against a real, currently-listed TradingView symbol page for that
  // exchange (not guessed) -- e.g. XETR:SAP, EURONEXT:MC, BMFBOVESPA:
  // PETR4, TSX:SHOP, SGX:D05, NSE:RELIANCE, ASX:BHP -- because a wrong
  // guess here is the same silent failure as not mapping it at all, just
  // harder to notice.
  //
  // Still NOT mapped, deliberately: continuous futures contracts (e.g.
  // 'ES=F') don't have a single stable TradingView equivalent; indices
  // (^XXX) need TradingView's own index codes, not Yahoo's; forex pairs
  // and smaller exchanges (Nordic, Warsaw, Madrid, Milan, etc.) weren't
  // re-verified this pass -- all of these honestly show a "not supported"
  // note instead of guessing wrong and displaying the wrong chart.
  function toTradingViewSymbol(raw) {
    if (!raw) return null;
    var s = String(raw).toUpperCase().trim();
    if (!s) return null;

    if (s.endsWith('-USD')) {
      var base = s.slice(0, -4);
      return 'BINANCE:' + base + 'USDT';
    }
    if (s.endsWith('.HK')) {
      var hkCode = s.slice(0, -3).replace(/^0+/, '');
      return 'HKEX:' + hkCode;
    }
    if (s.endsWith('.SS')) return 'SSE:' + s.slice(0, -3);
    if (s.endsWith('.SZ')) return 'SZSE:' + s.slice(0, -3);
    if (s.endsWith('.TW')) return 'TWSE:' + s.slice(0, -3);
    if (s.endsWith('.T')) return 'TSE:' + s.slice(0, -2);
    if (s.endsWith('.KS')) return 'KRX:' + s.slice(0, -3);
    if (s.endsWith('.L')) return 'LSE:' + s.slice(0, -2);
    if (s.endsWith('.AX')) return 'ASX:' + s.slice(0, -3);
    if (s.endsWith('.NS')) return 'NSE:' + s.slice(0, -3);
    if (s.endsWith('.BO')) return 'BSE:' + s.slice(0, -3);
    if (s.endsWith('.DE')) return 'XETR:' + s.slice(0, -3);
    if (s.endsWith('.SA')) return 'BMFBOVESPA:' + s.slice(0, -3);
    if (s.endsWith('.TO')) return 'TSX:' + s.slice(0, -3);
    if (s.endsWith('.SI')) return 'SGX:' + s.slice(0, -3);
    // Euronext is a single merged exchange in TradingView's listing --
    // Paris/Amsterdam/Brussels/Lisbon all resolve under one "EURONEXT:"
    // prefix (verified via EURONEXT:MC for Paris-listed LVMH).
    if (s.endsWith('.PA') || s.endsWith('.AS') || s.endsWith('.BR') || s.endsWith('.LS')) {
      return 'EURONEXT:' + s.slice(0, -3);
    }
    if (s.startsWith('^')) return null; // indices -- TradingView needs its own index codes, not Yahoo's ^XXX
    if (s.includes('=')) return null;   // continuous futures contracts -- no reliable 1:1 mapping
    if (s.includes('-') || s.includes('.')) return null; // anything else unmapped (forex pairs, smaller exchanges not yet verified)
    return s; // plain US ticker -- TradingView's widget resolves bare symbols fine
  }

  function currentTheme() {
    var attr = document.documentElement.getAttribute('data-theme');
    return attr === 'dark' ? 'dark' : 'light';
  }

  // 2026-07-19 fix: was hardcoded to 'zh_TW' regardless of the site's
  // selected UI language, so switching to English (or any other of the
  // 46 supported languages) still showed TradingView's own toolbar/axis
  // labels in Chinese ("ENGLISH 重有中文"). Only map to locales
  // TradingView's embed actually supports -- everything else honestly
  // falls back to English rather than silently defaulting to Chinese or
  // guessing an unsupported code.
  var TV_LOCALE_MAP = {
    'en': 'en', 'zh-TW': 'zh_TW', 'zh-HK': 'zh_TW', 'zh-CN': 'zh_CN',
    'ja': 'ja', 'ko': 'ko', 'es': 'es', 'fr': 'fr', 'de': 'de',
    'it': 'it', 'pt': 'pt', 'ru': 'ru', 'tr': 'tr', 'ar': 'ar',
    'th': 'th', 'vi': 'vi', 'id': 'id', 'pl': 'pl'
  };
  function currentTvLocale() {
    var lang = (typeof I18N !== 'undefined' && I18N.currentLang) || 'zh-HK';
    return TV_LOCALE_MAP[lang] || 'en';
  }

  function render(containerId, symbol) {
    var container = document.getElementById(containerId);
    if (!container) return;
    container.innerHTML = '';

    var tvSymbol = toTradingViewSymbol(symbol);
    if (!tvSymbol) {
      container.innerHTML = '<div style="padding:1rem;text-align:center;color:var(--text-muted,#666666);font-size:0.85rem">此資產類型暫未支援 TradingView 圖表顯示</div>';
      return;
    }

    var wrapper = document.createElement('div');
    wrapper.className = 'tradingview-widget-container';
    wrapper.style.height = '100%';

    var widgetDiv = document.createElement('div');
    widgetDiv.className = 'tradingview-widget-container__widget';
    widgetDiv.style.height = '100%';
    wrapper.appendChild(widgetDiv);

    var script = document.createElement('script');
    script.type = 'text/javascript';
    script.src = 'https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js';
    script.async = true;
    script.text = JSON.stringify({
      autosize: true,
      symbol: tvSymbol,
      interval: 'D',
      timezone: 'Etc/UTC',
      theme: currentTheme(),
      style: '1',
      locale: currentTvLocale(),
      allow_symbol_change: true,
      hide_side_toolbar: false,
      support_host: 'https://www.tradingview.com'
    });
    wrapper.appendChild(script);

    container.appendChild(wrapper);
  }

  window.renderTradingViewWidget = render;
  window.toTradingViewSymbol = toTradingViewSymbol;
})();
