!function () {
  // 2026-08-09 (task #731, AJ ref-image batch: "下面5個轉成跟CHAT ICON 一樣圓
  // ICON，統一一個ICON 指住滑出來，放右邊個CHAT ICON上面，手機也是"): full
  // redesign, replacing the previous bottom bar (edge-to-edge 3x2 grid on
  // mobile / centered pill on desktop -- see the removed history below)
  // with a single round trigger, styled like js/quick-ask-bubble.js's chat
  // bubble and positioned above it on the right edge (with
  // js/theme-toggle.js's round moon/sun icon now stacked in between the
  // two). Tapping the trigger slides the 6 widgets out ABOVE it as round
  // icon buttons ("右邊個加號向上滑出" -- follow-up from AJ after the first
  // version slid them out sideways); tapping again (or clicking outside)
  // collapses them back behind it. Same behavior on mobile and desktop.
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
  // 2026-08-10 (AJ: "＋滑出的皇冠換成每日市場快訊，並跟其他ICON排好"): the
  // "crown" AJ was asking about was actually points-badge.js's 🏅 medal
  // glyph on #xflPointsBadge. #freeSignalsBadge already links to
  // market-brief.html labelled "每日市場快訊" (nav_free_signals), so rather
  // than build a second icon with the same destination, xflPointsBadge is
  // dropped from the dock entirely -- leaving exactly 5 icons (TG/FB/
  // Share/每日市場快訊/Language), matching AJ's "顯示5個ICON" count.
  var DOCK_IDS = ["tgWidget", "fbWidget", "shareWidget", "freeSignalsBadge", "langSwitcher"];
  var STYLE_ID = "xflMobileDockStyle";
  var DOCK_ID = "xflMobileDock";
  var TRIGGER_ID = "xflDockTrigger";

  function ensureStyle() {
    if (document.getElementById(STYLE_ID)) return;
    var css =
      // 2026-08-10: column re-anchored after js/theme-toggle.js and
      // js/quick-ask-bubble.js moved down the right edge (AJ: "右邊ICON，
      // 底色放CHAT ICON下面"). New order bottom-to-top: #themeToggleBtn
      // (20/28px), #xflQabBtn (82/90px, +62), this trigger (144/152px,
      // +62) -- same column, same rhythm, just shifted down as a unit.
      "#" + DOCK_ID + "{position:fixed;right:20px;bottom:144px;z-index:1000;" +
        "display:flex;flex-direction:column;align-items:center;}" +
      "#" + TRIGGER_ID + "{order:99;width:48px;height:48px;border-radius:50%;flex-shrink:0;" +
        "background:var(--accent);color:#fff;border:none;cursor:pointer;" +
        "box-shadow:0 6px 20px rgba(var(--accent-rgb),0.4);display:flex;align-items:center;" +
        "justify-content:center;transition:transform 0.15s}" +
      "#" + TRIGGER_ID + ":hover{transform:scale(1.08)}" +
      "#" + TRIGGER_ID + " svg{transition:transform .25s ease}" +
      "#" + DOCK_ID + ".xfl-dock-open #" + TRIGGER_ID + " svg{transform:rotate(45deg)}" +
      // The 6 widget wrappers/badges themselves stay normal inline-flex
      // boxes (auto height, no transform) -- only their INNER round
      // trigger is what collapses, so a wrapper never becomes a
      // transformed containing block for its fixed-position panel.
      "#" + DOCK_ID + " #tgWidget,#" + DOCK_ID + " #fbWidget,#" + DOCK_ID + " #shareWidget," +
        "#" + DOCK_ID + " #langSwitcher{position:relative!important;top:auto!important;left:auto!important;" +
        "right:auto!important;bottom:auto!important;display:inline-flex!important;align-items:center;" +
        "flex-shrink:0;order:1}" +
      "#" + DOCK_ID + " #freeSignalsBadge{order:1;flex-shrink:0}" +
      // Shared round-icon look for all 5 collapsible triggers. Text is
      // zeroed out and replaced with a fixed emoji glyph per widget so
      // this never depends on whatever dynamic label the source script
      // last wrote into the element. Height (not width) is what animates
      // now, since the reveal direction is vertical (upward) -- width
      // stays fixed at 44px throughout.
      "#" + DOCK_ID + " #tgWidget>button,#" + DOCK_ID + " #fbWidget>button," +
        "#" + DOCK_ID + " #shareWidget>#shareWidgetBtn,#" + DOCK_ID + " #langSwitcher>button," +
        "#" + DOCK_ID + " #freeSignalsBadge{" +
        "width:44px;height:44px;max-height:44px;border-radius:50%!important;" +
        "display:flex!important;align-items:center;justify-content:center;padding:0!important;" +
        "font-size:0!important;line-height:1!important;box-shadow:0 4px 14px rgba(0,0,0,0.25)!important;" +
        "overflow:hidden;box-sizing:border-box;position:relative;flex-shrink:0;" +
        "transition:max-height .3s ease,opacity .3s ease,transform .3s ease,margin .3s ease;margin-bottom:8px;}" +
      // 2026-08-10 (AJ: "加號滑出 ICON 圖置中" -- the ::before glyphs were
      // drifting off-center inside their round buttons). Emoji glyphs
      // carry their own font-metric padding (ascent/descent + often extra
      // right-side advance width baked into the emoji font itself), so
      // centering them by font-size/line-height alone on an inline box
      // is unreliable -- it centers the FONT LINE BOX, not the visible
      // glyph. Making each ::before its own absolutely-positioned flex
      // box covering the full 44x44 button (the parent already has
      // position:relative from the shared rule above) centers the glyph
      // purely by box geometry instead, which is immune to emoji font
      // metric quirks.
      "#" + DOCK_ID + " #tgWidget>button::before,#" + DOCK_ID + " #fbWidget>button::before," +
        "#" + DOCK_ID + " #shareWidget>#shareWidgetBtn::before,#" + DOCK_ID + " #langSwitcher>button::before," +
        "#" + DOCK_ID + " #freeSignalsBadge::before{" +
        "position:absolute;top:0;left:0;width:100%;height:100%;display:flex;align-items:center;" +
        "justify-content:center;line-height:1}" +
      // 2026-08-10 (AJ: "TG 個飛機大D" -- make the TG plane icon bigger):
      // 19px -> 24px, the largest glyph in the dock now.
      "#" + DOCK_ID + " #tgWidget>button::before{content:'\\2708';font-size:24px}" +
      "#" + DOCK_ID + " #fbWidget>button::before{content:'\\1F4AC';font-size:18px}" +
      "#" + DOCK_ID + " #shareWidget>#shareWidgetBtn::before{content:'\\1F4E4';font-size:17px}" +
      "#" + DOCK_ID + " #langSwitcher>button::before{content:'\\1F310';font-size:18px}" +
      "#" + DOCK_ID + " #freeSignalsBadge::before{content:'\\1F3AF';font-size:18px}" +
      // Collapsed (default) state: zero height, invisible, unclickable --
      // this is what makes the trigger the only thing visible until
      // opened.
      "#" + DOCK_ID + ":not(.xfl-dock-open) #tgWidget>button,#" + DOCK_ID + ":not(.xfl-dock-open) #fbWidget>button," +
        "#" + DOCK_ID + ":not(.xfl-dock-open) #shareWidget>#shareWidgetBtn," +
        "#" + DOCK_ID + ":not(.xfl-dock-open) #langSwitcher>button," +
        "#" + DOCK_ID + ":not(.xfl-dock-open) #freeSignalsBadge{" +
        "max-height:0;margin-bottom:0;opacity:0;pointer-events:none;transform:scale(.4)}" +
      "#" + DOCK_ID + ".xfl-dock-open #tgWidget>button,#" + DOCK_ID + ".xfl-dock-open #fbWidget>button," +
        "#" + DOCK_ID + ".xfl-dock-open #shareWidget>#shareWidgetBtn," +
        "#" + DOCK_ID + ".xfl-dock-open #langSwitcher>button," +
        "#" + DOCK_ID + ".xfl-dock-open #freeSignalsBadge{" +
        "opacity:1;pointer-events:auto;transform:scale(1)}" +
      // 2026-08-10 (AJ: "這5個ICON向左滑出" -- each icon's own popup panel
      // opens to the LEFT of that icon, not floating above the whole
      // stack). Replaces the old shared `position:fixed;bottom:560px`
      // hack (which only worked for one fixed stack height) with
      // `position:absolute` anchored to each panel's own trigger wrapper
      // -- #tgWidget/#fbWidget/#shareWidget are the `position:relative`
      // wrappers set above (already position:relative!important via the
      // rule a few lines up), so `right:calc(100% + 10px)` places the
      // panel just to their left, vertically centered on the wrapper.
      "#tgPanel,#fbPanel,#sharePanel{position:absolute!important;left:auto!important;right:calc(100% + 10px)!important;" +
        "top:50%!important;bottom:auto!important;transform:translateY(-50%);width:min(280px,88vw)!important;" +
        "z-index:1001!important}" +
      "@media (max-width:768px){#" + DOCK_ID + "{bottom:152px}" +
        "#tgPanel,#fbPanel,#sharePanel{right:calc(100% + 6px)!important;width:min(260px,82vw)!important}}";
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

  // 2026-08-10 (AJ clarifying answer: "電腦指住就滑出，也可按，手機要按" --
  // on desktop, hovering a widget opens its side panel [can also click];
  // on mobile, tap is required). Rather than duplicate each widget's own
  // open/close logic (shareWidget's in particular rebuilds referral-link
  // hrefs on open), this calls the widget's REAL trigger button's
  // .click() on mouseenter/mouseleave -- reuses the exact existing
  // toggle behavior with zero risk of divergence. Gated by
  // matchMedia("(hover:hover)") so touch devices are unaffected and
  // still rely on tap.
  var HOVER_PANEL_WIDGETS = [
    { wrapId: "tgWidget", panelId: "tgPanel", btnSelector: "button" },
    { wrapId: "fbWidget", panelId: "fbPanel", btnSelector: "button" },
    { wrapId: "shareWidget", panelId: "sharePanel", btnSelector: "#shareWidgetBtn" }
  ];

  function isPanelOpen(panel) {
    return !(!panel || "none" === getComputedStyle(panel).display);
  }

  function wireHoverPanels() {
    if (!window.matchMedia || !window.matchMedia("(hover:hover)").matches) return;
    HOVER_PANEL_WIDGETS.forEach(function (w) {
      var wrap = document.getElementById(w.wrapId);
      if (!wrap || wrap.dataset.xflHoverWired) return;
      var panel = document.getElementById(w.panelId);
      var btn = wrap.querySelector(w.btnSelector);
      if (!panel || !btn) return;
      wrap.dataset.xflHoverWired = "1";
      var closeTimer = null;
      wrap.addEventListener("mouseenter", function () {
        clearTimeout(closeTimer);
        if (!isPanelOpen(panel)) btn.click();
      });
      wrap.addEventListener("mouseleave", function () {
        closeTimer = setTimeout(function () {
          if (isPanelOpen(panel)) btn.click();
        }, 150);
      });
    });
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
    // element even after a widget that loads asynchronously (i18n.js's
    // language switcher) gets docked later.
    dock.appendChild(ensureTrigger());
    wireHoverPanels();
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
