// XFINLAB "Daily Signals" floating badge (links to free-signals.html).
// Small fixed bottom-right pill, shown on every main page except
// free-signals.html itself (no point promoting the page you're already
// on). Right-side floating stack (bottom-up): TG Signals widget
// (#tgWidget, 24) -> this badge (80) -> language switcher (136,
// js/i18n.js) -> share widget (192, js/share-widget.js). Label text
// comes from the "nav_free_signals" i18n key, which now reads "Daily
// Signals" (renamed to disambiguate from the older Telegram promo
// widget, whose button used to say "Free Signals" and was renamed to
// "TG Signals" for the same reason).
(function () {
  if (/free-signals\.html$/i.test(location.pathname)) return;
  if (document.getElementById('freeSignalsBadge')) return;

  function label() {
    if (typeof I18N !== 'undefined' && I18N.translations && I18N.translations['nav_free_signals']) {
      return I18N.translations['nav_free_signals'];
    }
    return '訂閱每日信號';
  }

  function addBadge() {
    if (document.getElementById('freeSignalsBadge')) return;
    var a = document.createElement('a');
    a.id = 'freeSignalsBadge';
    a.href = 'free-signals.html';
    a.setAttribute('data-i18n', 'nav_free_signals');
    a.textContent = '🎯 ' + label();
    a.style.cssText = 'position:fixed;bottom:80px;right:24px;z-index:998;background:var(--accent-orange,#f59e0b);' +
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
