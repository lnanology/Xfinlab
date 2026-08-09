!function () {
  // 2026-08-02 fix (task #609, "手機UI 全部頁顯示跟第一張下面6個導航格式，
  // 可滑動時6個導航保持在底下嗎 登入頁除外"): every page independently
  // injects up to 6 fixed-position floating widgets -- TG Signals
  // (#tgWidget), Feedback (#fbWidget), points-badge.js's #xflPointsBadge,
  // share-widget.js's #shareWidget, free-signals-badge.js's
  // #freeSignalsBadge, and i18n.js's language switcher (#langSwitcher) --
  // each hardcoding its own screen corner with no shared coordination. On
  // narrow screens they overlap each other and page content (inputs,
  // buttons, result cards). This consolidates whichever of the 6 exist on
  // a given page into one fixed-bottom bar that stays pinned to the
  // viewport while the page scrolls, instead of floating independently.
  //
  // 2026-08-09 (AJ: "TG feedback share 每日資訊 語言 呢6個 置最底置中，
  // 框可以跟返電腦屏幕畫面做返闊D"): extended from mobile-only to ALSO
  // dock on desktop -- previously desktop kept each widget in its own
  // independent corner (see the now-removed `else if (dock)` restore
  // branch below). Desktop now gets the SAME bottom-center dock, styled
  // as a floating rounded pill bar (not edge-to-edge like mobile's 3x2
  // grid) whose width scales with the viewport via `min(88vw, 860px)` so
  // it visibly widens on a bigger monitor instead of staying a fixed
  // small size. login.html intentionally does not include this script.
  var DOCK_IDS = ["tgWidget", "fbWidget", "xflPointsBadge", "shareWidget", "freeSignalsBadge", "langSwitcher"];
  var STYLE_ID = "xflMobileDockStyle";
  var DOCK_ID = "xflMobileDock";

  function ensureStyle() {
    if (document.getElementById(STYLE_ID)) return;
    var css =
      // Base (mobile-first): edge-to-edge 3x2 grid bar pinned to the
      // viewport bottom, unchanged from the original mobile-only version.
      "#" + DOCK_ID + "{position:fixed;left:0;right:0;bottom:0;z-index:1000;" +
        "display:grid;grid-template-columns:repeat(3,1fr);gap:4px;" +
        "padding:6px 6px calc(6px + env(safe-area-inset-bottom,0px));" +
        "background:var(--bg-card,#fff);border-top:1px solid var(--border-color,#e2e8f0);" +
        "box-shadow:0 -4px 16px rgba(0,0,0,0.15)}" +
      "#" + DOCK_ID + ">*{position:relative!important;top:auto!important;left:auto!important;right:auto!important;bottom:auto!important;display:flex!important;flex-direction:column!important;align-items:center!important;justify-content:center!important;width:100%!important;margin:0!important}" +
      "#" + DOCK_ID + " button,#" + DOCK_ID + ">a{font-size:0.64rem!important;padding:6px 2px!important;white-space:nowrap!important;overflow:hidden;text-overflow:ellipsis;max-width:100%;border-radius:8px!important;box-shadow:none!important;width:100%!important;text-align:center!important}" +
      "#tgPanel,#fbPanel,#sharePanel,#langSwitcher>div:last-child{position:fixed!important;left:50%!important;right:auto!important;bottom:96px!important;top:auto!important;transform:translateX(-50%);width:min(280px,88vw)!important;z-index:1001!important}" +
      "body{padding-bottom:70px}" +
      // Desktop (>768px): swap the edge-to-edge grid for a floating,
      // centered, rounded pill bar -- one row of all 6 items, width
      // scales with viewport instead of a fixed size, doesn't reserve
      // body padding since it floats over content rather than pushing it
      // up (matches how the widgets already behaved independently
      // before this change).
      "@media (min-width:769px){" +
        "#" + DOCK_ID + "{left:50%;right:auto;bottom:20px;transform:translateX(-50%);" +
          "width:min(88vw,860px);grid-template-columns:repeat(6,1fr);gap:8px;" +
          "border:1px solid var(--border-color,#e2e8f0);border-radius:16px;" +
          "padding:8px 12px;box-shadow:0 8px 28px rgba(0,0,0,0.18)}" +
        "#" + DOCK_ID + " button,#" + DOCK_ID + ">a{font-size:0.72rem!important;padding:8px 4px!important}" +
        "#tgPanel,#fbPanel,#sharePanel,#langSwitcher>div:last-child{bottom:88px!important}" +
        "body{padding-bottom:0}" +
      "}";
    var style = document.createElement("style");
    style.id = STYLE_ID;
    style.textContent = css;
    document.head.appendChild(style);
  }

  function dockWidgets() {
    // Always dock, at every viewport width -- desktop no longer restores
    // widgets to their own independent fixed corners (that used to be
    // the `else if (dock)` branch here; removed since AJ asked for the
    // same bottom-center grouping on desktop too).
    var dock = document.getElementById(DOCK_ID);
    if (!dock) {
      dock = document.createElement("div");
      dock.id = DOCK_ID;
      document.body.appendChild(dock);
    }
    DOCK_IDS.forEach(function (id) {
      var el = document.getElementById(id);
      if (el && el.parentElement !== dock) dock.appendChild(el);
    });
  }

  function debounce(fn, ms) {
    var h;
    return function () {
      var args = arguments;
      clearTimeout(h);
      h = setTimeout(function () { fn.apply(null, args); }, ms);
    };
  }

  function init() {
    ensureStyle();
    dockWidgets();
    // Resize no longer needs to toggle docked-vs-restored (dock is now
    // permanent at every width) -- kept only so late viewport changes
    // don't need a reload; harmless no-op re-run otherwise.
    window.addEventListener("resize", debounce(dockWidgets, 200));
    // Some widgets are appended asynchronously by their own script
    // (points-badge.js waits on a fetch; i18n.js's language switcher
    // waits on the translations request), so this can't just run once --
    // a MutationObserver catches each widget the moment it actually
    // appears, however late that is, without needing to poll.
    if (document.body) {
      new MutationObserver(debounce(dockWidgets, 150)).observe(document.body, { childList: true });
    }
  }

  if ("loading" === document.readyState) {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
}();
