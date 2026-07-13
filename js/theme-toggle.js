// XFINLAB theme toggle -- dark (site default/brand) <-> light.
// Applies data-theme="light" on <html> to opt into the light palette
// defined in css/style.css; absence of the attribute (or "dark") uses
// the dark default. Persisted per-browser via localStorage so it sticks
// across pages and reloads.
(function () {
  var STORAGE_KEY = 'xfinlab_theme';

  function getTheme() {
    var saved = localStorage.getItem(STORAGE_KEY);
    return saved === 'light' ? 'light' : 'dark';
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

  function addThemeToggleButton() {
    if (document.getElementById('themeToggleBtn')) return;

    var btn = document.createElement('button');
    btn.id = 'themeToggleBtn';
    btn.type = 'button';
    btn.style.cssText = 'position:fixed;bottom:24px;right:24px;z-index:9997;background:var(--bg-card,#0d1525);border:1px solid var(--border-color,#1e2d45);color:var(--text-primary,#e2e8f0);padding:8px 14px;border-radius:8px;cursor:pointer;font-size:0.82rem;white-space:nowrap;box-shadow:0 2px 8px rgba(0,0,0,0.3);font-family:inherit;';
    btn.onclick = toggleTheme;
    updateButton(btn, getTheme());
    document.body.appendChild(btn);
  }

  window.toggleXfinlabTheme = toggleTheme;

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', addThemeToggleButton);
  } else {
    addThemeToggleButton();
  }
})();
