!function () {
  var STORAGE_KEY = "xfinlab_theme";

  function xflGroupInsert(navEl, el) {
    var ORDER = ["xflChatBtn", "xflGSearchBtn", "themeToggleBtn", "xflSettingsWrap"];
    var g = document.getElementById("xflTopRightGroup");
    if (!g) {
      g = document.createElement("div");
      g.id = "xflTopRightGroup";
      navEl.appendChild(g);
    }
    var idx = ORDER.indexOf(el.id), before = null;
    for (var i = 0; i < g.children.length; i++) {
      var cIdx = ORDER.indexOf(g.children[i].id);
      if (cIdx > -1 && cIdx > idx) { before = g.children[i]; break; }
    }
    return before ? g.insertBefore(el, before) : g.appendChild(el), g;
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

  function renderLabel(btn, theme) {
    if (!btn) return;
    var label = "dark" === theme ? tt("theme_toggle_light", "☀️ Light") : tt("theme_toggle_dark", "🌙 Dark");
    var aria = "dark" === theme ? tt("theme_aria_switch_light", "Switch to light theme") : tt("theme_aria_switch_dark", "Switch to dark theme");
    btn.textContent = label;
    btn.setAttribute("aria-label", aria);
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
    } else {
      btn = document.createElement("button");
      btn.id = "themeToggleBtn";
      btn.type = "button";
      btn.onclick = toggleTheme;
      renderLabel(btn, getTheme());
      var navLinks = document.querySelector(".nav-links") || document.querySelector(".nav-right");
      var nav = (navLinks && navLinks.closest("nav")) || document.querySelector("nav");
      if (nav) {
        btn.style.cssText = "background:var(--bg-card,#0d1525);border:1px solid var(--border-color,#1e2d45);color:var(--text-primary,#e2e8f0);padding:6px 12px;border-radius:8px;cursor:pointer;font-size:0.8rem;white-space:nowrap;font-family:inherit;flex-shrink:0;";
        xflGroupInsert(nav, btn);
      } else {
        btn.style.cssText = "position:fixed;top:12px;right:16px;z-index:9997;background:var(--bg-card,#0d1525);border:1px solid var(--border-color,#1e2d45);color:var(--text-primary,#e2e8f0);padding:8px 14px;border-radius:8px;cursor:pointer;font-size:0.82rem;white-space:nowrap;box-shadow:0 2px 8px rgba(0,0,0,0.3);font-family:inherit;";
        document.body.appendChild(btn);
      }
    }
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
