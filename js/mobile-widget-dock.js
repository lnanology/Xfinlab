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
  // a given page into one fixed-bottom 3-column grid bar that stays
  // pinned to the viewport bottom while the page scrolls, instead of
  // floating independently. Desktop is untouched -- widgets keep their
  // original fixed corners there. Ported from chat.html's task #382 pilot
  // into one shared file so every page benefits identically instead of
  // duplicating this logic per page; login.html intentionally does not
  // include this script.
  var DOCK_IDS = ["tgWidget", "fbWidget", "xflPointsBadge", "shareWidget", "freeSignalsBadge", "langSwitcher"];
  var STYLE_ID = "xflMobileDockStyle";
  var DOCK_ID = "xflMobileDock";

  function ensureStyle() {
    if (document.getElementById(STYLE_ID)) return;
    var css = "@media (max-width:768px){" +
      "#" + DOCK_ID + "{position:fixed;left:0;right:0;bottom:0;z-index:1000;display:grid;grid-template-columns:repeat(3,1fr);gap:4px;padding:6px 6px calc(6px + env(safe-area-inset-bottom,0px));background:var(--bg-card,#fff);border-top:1px solid var(--border-color,#e2e8f0);box-shadow:0 -4px 16px rgba(0,0,0,0.15)}" +
      "#" + DOCK_ID + ">*{position:relative!important;top:auto!important;left:auto!important;right:auto!important;bottom:auto!important;display:flex!important;flex-direction:column!important;align-items:center!important;justify-content:center!important;width:100%!important;margin:0!important}" +
      "#" + DOCK_ID + " button,#" + DOCK_ID + ">a{font-size:0.64rem!important;padding:6px 2px!important;white-space:nowrap!important;overflow:hidden;text-overflow:ellipsis;max-width:100%;border-radius:8px!important;box-shadow:none!important;width:100%!important;text-align:center!important}" +
      "#tgPanel,#fbPanel,#sharePanel,#langSwitcher>div:last-child{position:fixed!important;left:50%!important;right:auto!important;bottom:96px!important;top:auto!important;transform:translateX(-50%);width:min(280px,88vw)!important;z-index:1001!important}" +
      "body{padding-bottom:70px}" +
      "}";
    var style = document.createElement("style");
    style.id = STYLE_ID;
    style.textContent = css;
    document.head.appendChild(style);
  }

  function dockWidgets() {
    var isMobile = window.matchMedia("(max-width: 768px)").matches;
    var dock = document.getElementById(DOCK_ID);
    if (isMobile) {
      if (!dock) {
        dock = document.createElement("div");
        dock.id = DOCK_ID;
        document.body.appendChild(dock);
      }
      DOCK_IDS.forEach(function (id) {
        var el = document.getElementById(id);
        if (el && el.parentElement !== dock) dock.appendChild(el);
      });
    } else if (dock) {
      // crossed back to desktop width (e.g. rotating a tablet) -- restore
      // each widget as a direct body child so it returns to its own
      // original fixed corner instead of staying grid-docked.
      Array.prototype.slice.call(dock.children).forEach(function (el) {
        document.body.appendChild(el);
      });
    }
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
