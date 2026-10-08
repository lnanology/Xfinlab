// 2026-08-10 (task #747, AJ: "所有卡片有資產的都加細K線小圖" -- 全站所有頁).
// Shared momentum-sparkline utility, extracted from index.html's original
// renderTopOppSparkline() (task #723, Top Opportunity cards only) so every
// asset-card location site-wide (screener/portfolio/company-compare/anomaly
// results, chat.html's on-demand asset card, dashboard.html watchlist, and
// per-ticker SEO pages) can render the same small SVG polyline chart from
// whatever last-N-closes array their own API response already returns --
// no chart library, no extra network calls, purely a tiny visual cue (the
// real chart is TradingView on ai-analysis.html/chart-analysis.html).
//
// Usage:
//   <script src="js/sparkline.js"></script>
//   ...
//   el.innerHTML = XflSparkline.render(item.sparkline, 'bull');
//   // or derive the direction class from whatever your data actually has:
//   XflSparkline.dirClass('偏多')      -> 'bull'
//   XflSparkline.dirClass('BUY')       -> 'bull'
//   XflSparkline.dirClass(+1.8)        -> 'bull'   (numeric % change)
//   XflSparkline.dirClass('偏空')      -> 'bear'
//   XflSparkline.dirClass(-0.4)        -> 'bear'
//   XflSparkline.dirClass(undefined)   -> 'neutral'
!function (global) {
  var STYLE_ID = "xflSparklineStyle";

  function ensureStyle() {
    if (document.getElementById(STYLE_ID)) return;
    var css =
      // Base size is 100x30 (matches the original Top Opportunity card
      // sparkline) -- callers that need a different footprint just size
      // the wrapping element and pass width/height to render(); the SVG's
      // viewBox scales to fit via preserveAspectRatio="none".
      ".xfl-spark{width:100%;height:34px;margin:4px 0 8px;display:block}" +
      ".xfl-spark polyline{fill:none;stroke-width:1.6}" +
      ".xfl-spark.bull polyline{stroke:var(--green,#22c55e)}" +
      ".xfl-spark.bear polyline{stroke:var(--red,#ef4444)}" +
      ".xfl-spark.neutral polyline{stroke:var(--amber,#f59e0b)}" +
      // Compact modifier for tighter card layouts (screener/company-compare
      // result rows, chat.html's inline asset card) that don't have room
      // for the full 34px-tall version.
      ".xfl-spark.xfl-spark-sm{height:22px;margin:2px 0 4px}";
    var style = document.createElement("style");
    style.id = STYLE_ID;
    style.textContent = css;
    document.head.appendChild(style);
  }

  // arr: array of numbers (closes/prices, oldest-first). dirClass: 'bull'
  // | 'bear' | 'neutral' (use dirClass() below to derive it consistently).
  // opts: { width, height, pad, className } all optional.
  function render(arr, dirClass, opts) {
    if (!Array.isArray(arr) || arr.length < 2) return "";
    ensureStyle();
    opts = opts || {};
    var w = opts.width || 100;
    var h = opts.height || 30;
    var pad = opts.pad != null ? opts.pad : 2;
    var cls = "xfl-spark " + (dirClass || "neutral") + (opts.className ? " " + opts.className : "");
    var min = Math.min.apply(null, arr);
    var max = Math.max.apply(null, arr);
    var range = (max - min) || 1;
    var pts = arr.map(function (v, i) {
      var x = pad + (i / (arr.length - 1)) * (w - pad * 2);
      var y = h - pad - ((v - min) / range) * (h - pad * 2);
      return x.toFixed(1) + "," + y.toFixed(1);
    }).join(" ");
    return '<svg class="' + cls + '" viewBox="0 0 ' + w + ' ' + h + '" preserveAspectRatio="none"><polyline points="' + pts + '"/></svg>';
  }

  // Normalizes whatever "direction"-ish value a page already has (Chinese
  // 偏多/偏空/中性 confluence labels, English BUY/SELL/HOLD-style words, or
  // a raw numeric % change) into the 3 CSS classes above.
  function dirClass(value) {
    if (value == null || value === "") return "neutral";
    if (typeof value === "number") {
      if (value > 0) return "bull";
      if (value < 0) return "bear";
      return "neutral";
    }
    var s = String(value).trim().toLowerCase();
    if (s === "偏多" || s === "bull" || s === "buy" || s === "up" || s === "long") return "bull";
    if (s === "偏空" || s === "bear" || s === "sell" || s === "down" || s === "short") return "bear";
    return "neutral";
  }

  global.XflSparkline = { render: render, dirClass: dirClass, ensureStyle: ensureStyle };
}(window);
