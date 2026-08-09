!function () {
  // 2026-08-09 (task #731, AJ ref-image batch: "下面5個轉成跟CHAT ICON 一樣圓
  // ICON，統一一個ICON 指住滑出來，放右邊個CHAT ICON上面，手機也是"): full
  // redesign, replacing the previous bottom bar (edge-to-edge 3x2 grid on
  // mobile / centered pill on desktop -- see the removed history below)
  // with a single round trigger, styled like js/quick-ask-bubble.js's chat
  // bubble and positioned directly above it on the right edge. Tapping the
  // trigger slides the 6 widgets out to its LEFT as round icon buttons;
  // tapping again (or clicking outside) collapses them back behind it.
  // Same behavior on mobile and desktop now -- no more separate layouts.
  //
  // Each widget keeps its own existing brand color and click behavior
  // (TG panel, Feedback panel, Share panel/QR modal, Language modal all
  // still work exactly as before) -- this only changes their outer shape
  // and how they're revealed. Four of the six widgets are wrapper <div>s
  // that also contain a popup panel positioned via `position:fixed`
  // (#tgWidget/#fbWidget/#shareWidget/#langSwitcher) -- the collapse/
  // reveal animation is applied to the inner trigger BUTTON inside each
  // wrapper, never to the wrapper itself, specifically to avoid CSS
  // `transform` on the wrapper turning it into a containing block for
  // its `position:fixed` panel child (that would silently break the
  // panel's fixed positioning). The other two widgets (#xflPointsBadge,
  // #freeSignalsBadge) have no such child panel, so they're animated
  // directly.
  //
  // Each original trigger renders a dynamic text label alongside its
  // emoji (e.g. "✈️ TG Updates", and for 3 of them the emoji+label is a
  // single text node rewritten by that widget's own script on every
  // i18n/points update -- there's no separate <span> to hide via CSS).
  // Rather than touch those other files' render logic, this collapses
  // the whole label to invisible (`font-size:0`) and draws a fixed icon
  // glyph via `::before` instead -- so it stays correct regardless of
  // what text the source widget currently has rendered.
  var DOCK_IDS = ["tgWidget", "fbWidget", "xflPointsBadge", "shareWidget", "freeSignalsBadge", "langSwitcher"];
  var STYLE_ID = "xflMobileDockStyle";
  var DOCK_ID = "xflMobileDock";
  var TRIGGER_ID = "xflDockTrigger";

  function ensureStyle() {
    if (document.getElementById(STYLE_ID)) return;
    var css =
      // Row anchored to the right edge, directly above quick-ask-bubble's
      // #xflQabBtn (bottom:96/104px, 52px tall -- see js/quick-ask-
      // bubble.js) with the same +62px gap that bubble uses for its own
      // panel, so the two round triggers read as one connected column.
      "#" + DOCK_ID + "{position:fixed;right:20px;bottom:158px;z-index:1000;" +
        "display:flex;align-items:center;}" +
      "#" + TRIGGER_ID + "{order:99;width:48px;height:48px;border-radius:50%;flex-shrink:0;" +
        "background:var(--accent);color:#fff;border:none;cursor:pointer;" +
        "box-shadow:0 6px 20px rgba(var(--accent-rgb),0.4);display:flex;align-items:center;" +
        "justify-content:center;transition:transform 0.15s}" +
      "#" + TRIGGER_ID + ":hover{transform:scale(1.08)}" +
      "#" + TRIGGER_ID + " svg{transition:transform .25s ease}" +
      "#" + DOCK_ID + ".xfl-dock-open #" + TRIGGER_ID + " svg{transform:rotate(45deg)}" +
      // The 6 widget wrappers/badges themselves stay normal inline-flex
      // boxes (auto width, no transform) -- only their INNER round
      // trigger is what collapses, so a wrapper never becomes a
      // transformed containing block for its fixed-position panel.
      "#" + DOCK_ID + " #tgWidget,#" + DOCK_ID + " #fbWidget,#" + DOCK_ID + " #shareWidget," +
        "#" + DOCK_ID + " #langSwitcher{position:relative!important;top:auto!important;left:auto!important;" +
        "right:auto!important;bottom:auto!important;display:inline-flex!important;align-items:center;" +
        "flex-shrink:0;order:1}" +
      "#" + DOCK_ID + " #xflPointsBadge,#" + DOCK_ID + " #freeSignalsBadge{order:1;flex-shrink:0}" +
      // Shared round-icon look for all 6 collapsible triggers. Text is
      // zeroed out and replaced with a fixed emoji glyph per widget so
      // this never depends on whatever dynamic label the source script
      // last wrote into the element.
      "#" + DOCK_ID + " #tgWidget>button,#" + DOCK_ID + " #fbWidget>button," +
        "#" + DOCK_ID + " #shareWidget>#shareWidgetBtn,#" + DOCK_ID + " #langSwitcher>button," +
        "#" + DOCK_ID + " #xflPointsBadge,#" + DOCK_ID + " #freeSignalsBadge{" +
        "width:44px;height:44px;max-width:44px;border-radius:50%!important;" +
        "display:flex!important;align-items:center;justify-content:center;padding:0!important;" +
        "font-size:0!important;line-height:1!important;box-shadow:0 4px 14px rgba(0,0,0,0.25)!important;" +
        "overflow:hidden;box-sizing:border-box;position:relative;" +
        "transition:max-width .3s ease,opacity .3s ease,transform .3s ease,margin .3s ease;margin-right:8px;}" +
      "#" + DOCK_ID + " #tgWidget>button::before{content:'\\2708';font-size:19px}" +
      "#" + DOCK_ID + " #fbWidget>button::before{content:'\\1F4AC';font-size:18px}" +
      "#" + DOCK_ID + " #shareWidget>#shareWidgetBtn::before{content:'\\1F4E4';font-size:17px}" +
      "#" + DOCK_ID + " #langSwitcher>button::before{content:'\\1F310';font-size:18px}" +
      "#" + DOCK_ID + " #xflPointsBadge::before{content:'\\1F3C5';font-size:18px}" +
      "#" + DOCK_ID + " #freeSignalsBadge::before{content:'\\1F3AF';font-size:18px}" +
      // Collapsed (default) state: zero width, invisible, unclickable --
      // this is what makes the trigger the only thing visible until
      // opened.
      "#" + DOCK_ID + ":not(.xfl-dock-open) #tgWidget>button,#" + DOCK_ID + ":not(.xfl-dock-open) #fbWidget>button," +
        "#" + DOCK_ID + ":not(.xfl-dock-open) #shareWidget>#shareWidgetBtn," +
        "#" + DOCK_ID + ":not(.xfl-dock-open) #langSwitcher>button," +
        "#" + DOCK_ID + ":not(.xfl-dock-open) #xflPointsBadge," +
        "#" + DOCK_ID + ":not(.xfl-dock-open) #freeSignalsBadge{" +
        "max-width:0;margin-right:0;opacity:0;pointer-events:none;transform:scale(.4)}" +
      "#" + DOCK_ID + ".xfl-dock-open #tgWidget>button,#" + DOCK_ID + ".xfl-dock-open #fbWidget>button," +
        "#" + DOCK_ID + ".xfl-dock-open #shareWidget>#shareWidgetBtn," +
        "#" + DOCK_ID + ".xfl-dock-open #langSwitcher>button," +
        "#" + DOCK_ID + ".xfl-dock-open #xflPointsBadge," +
        "#" + DOCK_ID + ".xfl-dock-open #freeSignalsBadge{" +
        "opacity:1;pointer-events:auto;transform:scale(1)}" +
      // Popup panels (TG/Feedback/Share) float above the row, same
      // pattern as before, just re-anchored to the new row position.
      "#tgPanel,#fbPanel,#sharePanel{position:fixed!important;left:auto!important;right:20px!important;" +
        "bottom:220px!important;top:auto!important;width:min(280px,88vw)!important;z-index:1001!important}" +
      "@media (max-width:768px){#" + DOCK_ID + "{bottom:168px}#tgPanel,#fbPanel,#sharePanel{bottom:230px}}";
    var style = document.createElement("style");
    style.id = STYLE_ID;
    style.textContent = css;
    document.head.appendChild(style);
  }

  function ensureTrigger() {
    var btn = document.getElementById(TRIGGER_ID);
    if (btn) return btn;
    btn = document.createElement("button");
    btn.id = TRIGGER_ID;
    btn.type = "button";
    btn.setAttribute("aria-label", "More");
    btn.innerHTML = '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"></line><line x1="5" y1="12" x2="19" y2="12"></line></svg>';
    btn.addEventListener("click", function (e) {
      e.stopPropagation();
      document.getElementById(DOCK_ID).classList.toggle("xfl-dock-open");
    });
    document.addEventListener("click", function (e) {
      var dock = document.getElementById(DOCK_ID);
      if (dock && dock.classList.contains("xfl-dock-open") && !dock.contains(e.target)) {
        dock.classList.remove("xfl-dock-open");
      }
    });
    document.addEventListener("keydown", function (e) {
      var dock = document.getElementById(DOCK_ID);
      if (e.key === "Escape" && dock) dock.classList.remove("xfl-dock-open");
    });
    return btn;
  }

  function dockWidgets() {
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
    // Re-append the trigger last on every run (appendChild on an
    // existing child just moves it) so it always stays the rightmost
    // element even after a widget that loads asynchronously (points-
    // badge.js, i18n.js's language switcher) gets docked later.
    dock.appendChild(ensureTrigger());
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
