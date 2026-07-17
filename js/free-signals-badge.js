// XFINLAB Free Signals floating badge.
// Small fixed bottom-right pill linking to free-signals.html, shown on
// every main page except free-signals.html itself (no point promoting
// the page you're already on). Mirrors the existing floating-widget
// pattern (points-badge bottom-left, feedback bottom-left) but sits
// bottom-right, since js/theme-toggle.js now lives top-right instead.
(function () {
  if (/free-signals\.html$/i.test(location.pathname)) return;
  if (document.getElementById('freeSignalsBadge')) return;

  function label() {
    if (typeof I18N !== 'undefined' && I18N.translations && I18N.translations['nav_free_signals']) {
      return I18N.translations['nav_free_signals'];
    }
    return '免費訊號';
  }

  function addBadge() {
    if (document.getElementById('freeSignalsBadge')) return;
    var a = document.createElement('a');
    a.id = 'freeSignalsBadge';
    a.href = 'free-signals.html';
    a.setAttribute('data-i18n', 'nav_free_signals');
    a.textContent = '🎯 ' + label();
    a.style.cssText = 'position:fixed;bottom:24px;right:24px;z-index:9996;background:var(--accent-orange,#f59e0b);' +
      'color:#0d1525;padding:10px 16px;border-radius:24px;font-weight:600;font-size:0.85rem;' +
      'text-decoration:none;white-space:nowrap;box-shadow:0 2px 10px rgba(0,0,0,0.35);font-family:inherit;';
    document.body.appendChild(a);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', addBadge);
  } else {
    addBadge();
  }
})();
