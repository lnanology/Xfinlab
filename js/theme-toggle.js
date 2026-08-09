!function () {
  var STORAGE_KEY = "xfinlab_theme";
  var STYLE_ID = "xflThemeBtnStyle";

  // 2026-08-09 (AJ ref-image follow-up: "底色ICON 月亮 放 加號下面 跟CHAT
  // ICON"): this used to live inside the topbar (#xflTopRightGroup, next
  // to the search icon/Account widget -- see the removed xflGroupInsert()
  // copy that lived here). AJ asked for it to leave the topbar entirely
  // and join the floating round-icon column on the right edge instead --
  // stacked directly above js/quick-ask-bubble.js's chat bubble, below
  // js/mobile-widget-dock.js's "+" trigger. It's now always a fixed round
  // button (never inserted into <nav>) so this file no longer needs to
  // care whether a page has a <nav>/.nav-links at all.
  function ensureStyle() {
    if (document.getElementById(STYLE_ID)) return;
    var css =
      "#themeToggleBtn{position:fixed;right:20px;bottom:158px;z-index:1000;width:48px;height:48px;" +
        "border-radius:50%;background:var(--bg-card,#0d1525);border:1px solid var(--border-color,#1e2d45);" +
        "color:var(--text-primary,#e2e8f0);cursor:pointer;display:flex;align-items:center;justify-content:center;" +
        "padding:0;box-shadow:0 4px 14px rgba(0,0,0,0.25);transition:transform .15s,border-color .2s,color .2s}" +
      "#themeToggleBtn:hover{border-color:var(--accent-orange,#f59e0b);color:var(--accent-orange,#f59e0b);transform:scale(1.08)}" +
      "#themeToggleBtn svg{margin:0!important}" +
      "@media (max-width:768px){#themeToggleBtn{bottom:166px}}";
    var style = document.createElement("style");
    style.id = STYLE_ID;
    style.textContent = css;
    document.head.appendChild(style);
  }

  function getTheme() {
    return "dark" === localStorage.getItem(STORAGE_KEY) ? "dark" : "light";
  }

  var currentTheme = getTheme();

  // 2026-07-31 fix ("DARK" staying in English on every non-English UI):
  // this button's label/aria-label used to be hardcoded literal English
  // strings ("☀️ Light" / "🌙 Dark") with zero regard for I18N.currentLang,
  // unlike every other piece of UI chrome on the site. Now looks up
  // theme_toggle_light/theme_toggle_dark (and their aria-label
  // counterparts) from services/i18n.py's per-language dict via the
  // client-side I18N object, falling back to the original English text
  // when I18N isn't loaded yet or a translation is missing.
  function tt(key, fallback) {
    return (typeof I18N !== "undefined" && I18N.translations && I18N.translations[key]) || fallback;
  }

  // 2026-08-01 ("ICON圖案...建議全站用SVG Icons"): every language's
  // theme_toggle_light/dark string has "☀️ "/"🌙 " baked into the
  // translated text itself (services/i18n.py, all 47 languages) --
  // emoji render inconsistently across OS/browser and can't be
  // recolored via CSS. Strip that leading emoji+space here (Unicode
  // property escape, matches any pictographic char + optional variation
  // selector) and prepend a proper inline SVG (sun/moon, Lucide-style,
  // currentColor) instead -- zero i18n.py changes needed since every
  // language keeps its own translated word after the emoji.
  var ICON_SUN = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="4"></circle><path d="M12 2v2"></path><path d="M12 20v2"></path><path d="m4.93 4.93 1.41 1.41"></path><path d="m17.66 17.66 1.41 1.41"></path><path d="M2 12h2"></path><path d="M20 12h2"></path><path d="m6.34 17.66-1.41 1.41"></path><path d="m19.07 4.93-1.41 1.41"></path></svg>';
  var ICON_MOON = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"></path></svg>';

  // 2026-08-09: label text dropped (button is icon-only now, round style
  // matching the chat bubble/dock trigger) -- aria-label keeps the
  // translated text for accessibility, stripEmoji() is no longer needed
  // since nothing renders theme_toggle_light/dark's text any more.
  function renderLabel(btn, theme) {
    if (!btn) return;
    var aria = "dark" === theme ? tt("theme_aria_switch_light", "Switch to light theme") : tt("theme_aria_switch_dark", "Switch to dark theme");
    var icon = "dark" === theme ? ICON_SUN : ICON_MOON;
    btn.innerHTML = icon;
    btn.setAttribute("aria-label", aria);
    btn.title = aria;
  }

  function toggleTheme() {
    var next = "dark" === getTheme() ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    localStorage.setItem(STORAGE_KEY, next);
    renderLabel(document.getElementById("themeToggleBtn"), next);
  }

  function isVisible(el) {
    return !(!el || null === el.offsetParent);
  }

  function ensureButton() {
    var btn = document.getElementById("themeToggleBtn");
    if (btn) {
      renderLabel(btn, getTheme());
      return;
    }
    ensureStyle();
    btn = document.createElement("button");
    btn.id = "themeToggleBtn";
    btn.type = "button";
    btn.onclick = toggleTheme;
    renderLabel(btn, getTheme());
    document.body.appendChild(btn);
  }

  function deferInit() { setTimeout(ensureButton, 0); }

  document.documentElement.setAttribute("data-theme", currentTheme);
  window.toggleXfinlabTheme = toggleTheme;
  // Re-render the button label whenever i18n finishes loading or the
  // language is switched, so "Dark"/"Light" updates without a page reload.
  document.addEventListener("i18nApplied", function () {
    renderLabel(document.getElementById("themeToggleBtn"), getTheme());
  });
  if ("loading" === document.readyState) {
    document.addEventListener("DOMContentLoaded", deferInit);
  } else {
    deferInit();
  }
}();
