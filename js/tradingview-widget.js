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
  // Best-effort mapping from XFINLAB's internal ticker format to
  // TradingView's EXCHANGE:SYMBOL format. Not exhaustive -- continuous
  // futures contracts (e.g. 'ES=F') don't have a single stable TradingView
  // equivalent, so those honestly show a "not supported" note instead of
  // guessing wrong and showing the wrong chart.
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
    if (s.startsWith('^')) return null; // indices -- TradingView needs its own index codes, not Yahoo's ^XXX
    if (s.includes('=')) return null;   // continuous futures contracts -- no reliable 1:1 mapping
    if (s.includes('-') || s.includes('.')) return null; // anything else unmapped (forex pairs etc.)
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
