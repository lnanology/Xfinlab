// XFINLAB theme toggle -- light (site default, 2026-07-18: white bg,
// black text, black border) <-> dark (brand palette, opt-in).
// Applies data-theme="dark" on <html> to opt into the dark palette
// defined in css/style.css; absence of the attribute (or "light") uses
// the light default. Persisted per-browser via localStorage so it sticks
// across pages and reloads.
//
// Placement (2026-07): previously a fixed bottom-right floating button
// on every page. Per feedback, the toggle now lives top-right, as the
// immediate previous sibling of whichever "Account" widget the current
// page has (js/nav.js's shared #xflSettingsWrap, index.html's own
// #topbarSettingsWrap, or dashboard.html's own #accountBtn) -- so it
// visually reads as "Light/Dark, then Account" in the same row. Pages
// with no signed-in Account widget (guests, or pages without one at
// all) still get the toggle, just as a small fixed top-right button
// instead of floating bottom-right.
(function () {
  var STORAGE_KEY = 'xfinlab_theme';

  function getTheme() {
    var saved = localStorage.getItem(STORAGE_KEY);
    return saved === 'dark' ? 'dark' : 'light';
  }

  // Set the attribute as early as possible (script runs synchronously in
  // <head>, before body paints) to avoid a flash of the wrong theme.
  var initialTheme = getTheme();
  document.documentElement.setAttribute('data-theme', initialTheme);

  function updateButton(btn, theme) {
    if (!btn) return;
    btn.textContent = theme === 'dark' ? '☀️ Light' : '🌙 Dark';
    btn.setAttribute('aria-label', theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme');
  }

  function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem(STORAGE_KEY, theme);
    updateButton(document.getElementById('themeToggleBtn'), theme);
  }

  function toggleTheme() {
    applyTheme(getTheme() === 'dark' ? 'light' : 'dark');
  }

  // "Visible" here just means "not currently display:none up the
  // ancestor chain" -- offsetParent is null both for display:none
  // elements and for position:fixed ones, but none of our anchor
  // candidates are position:fixed themselves, so this is a safe,
  // dependency-free visibility check.
  function isVisible(el) {
    return !!(el && el.offsetParent !== null);
  }

  function findAccountAnchor() {
    var candidates = [
      document.getElementById('xflSettingsWrap'),   // js/nav.js shared widget
      document.getElementById('topbarSettingsWrap'), // index.html's own topbar
      document.getElementById('accountBtn')          // dashboard.html's own dropdown
    ];
    for (var i = 0; i < candidates.length; i++) {
      if (isVisible(candidates[i])) return candidates[i];
    }
    return null;
  }

  function styleInline(btn) {
    btn.style.cssText = 'background:var(--bg-card,#0d1525);border:1px solid var(--border-color,#1e2d45);' +
      'color:var(--text-primary,#e2e8f0);padding:6px 12px;border-radius:8px;cursor:pointer;font-size:0.8rem;' +
      'white-space:nowrap;font-family:inherit;margin-right:10px;flex-shrink:0;';
  }

  function styleFixedTopRight(btn) {
    btn.style.cssText = 'position:fixed;top:12px;right:16px;z-index:9997;background:var(--bg-card,#0d1525);' +
      'border:1px solid var(--border-color,#1e2d45);color:var(--text-primary,#e2e8f0);padding:8px 14px;' +
      'border-radius:8px;cursor:pointer;font-size:0.82rem;white-space:nowrap;' +
      'box-shadow:0 2px 8px rgba(0,0,0,0.3);font-family:inherit;';
  }

  function addThemeToggleButton() {
    var existing = document.getElementById('themeToggleBtn');
    if (existing) { updateButton(existing, getTheme()); return; }

    var btn = document.createElement('button');
    btn.id = 'themeToggleBtn';
    btn.type = 'button';
    btn.onclick = toggleTheme;
    updateButton(btn, getTheme());

    var anchor = findAccountAnchor();
    if (anchor && anchor.parentNode) {
      styleInline(btn);
      anchor.parentNode.insertBefore(btn, anchor);
    } else {
      styleFixedTopRight(btn);
      document.body.appendChild(btn);
    }
  }

  // Deferred one macrotask past DOMContentLoaded: other DOMContentLoaded
  // listeners registered before this one (e.g. js/nav.js's own
  // injectUserTopbarFlyout, which builds #xflSettingsWrap) run
  // synchronously during the same event dispatch, so by the time this
  // setTimeout(...,0) callback fires, any Account widget the page is
  // going to inject this pageview already exists -- letting
  // findAccountAnchor() actually find it instead of racing it.
  function deferredInit() {
    setTimeout(addThemeToggleButton, 0);
  }

  window.toggleXfinlabTheme = toggleTheme;

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', deferredInit);
  } else {
    deferredInit();
  }
})();
