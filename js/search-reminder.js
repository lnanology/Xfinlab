// XFINLAB post-search "subscribe daily signals" reminder banner.
//
// Distinct from the other two subscribe touchpoints already on the site:
//   - js/free-signals-badge.js: always-visible orange pill, bottom-right.
//   - js/push-prompt.js: timed bottom-center toast, shown ~2.5s after load.
// This one is plain/neutral (black border + black text following the
// page's own fg/border colors -- no accent color), and only appears once
// the visitor actually performs a search/analysis action on the page.
// It's inserted directly below the top <nav> bar (left-aligned, in normal
// document flow -- literally "hangs under the XFINLAB bar"), stays until
// the page navigates away (no auto-timeout), and if the visitor dismisses
// it, it reappears the next time a search fires on the same page.
//
// Hooked generically via window.trackEvent('search', ...) -- every
// search-driven page (index.html demo box, dashboard.html, stress-lab.html,
// chart-analysis.html, anomaly.html, portfolio.html, ...) already calls
// this for analytics, so wrapping it here covers all of them without
// editing each page's individual search handler.
//
// IMPORTANT: must load AFTER js/nav.js on every page (nav.js defines the
// real window.trackEvent only if it isn't already defined) -- placed near
// the end of <body>, same spot as js/cookie-consent.js.
(function () {
  if (/free-signals\.html$/i.test(location.pathname)) return;

  function t(key, fallback) {
    return (typeof I18N !== 'undefined' && I18N.translations && I18N.translations[key]) || fallback;
  }

  function buildBanner() {
    var bar = document.createElement('div');
    bar.id = 'xflSearchReminder';
    bar.style.cssText = 'display:flex;align-items:center;gap:10px;' +
      'background:var(--bg-card,#FFFFFF);border:1px solid var(--border-color,#000000);' +
      'color:var(--text-primary,#000000);border-radius:8px;padding:8px 14px;margin:10px 1.5rem 0;' +
      'font-size:0.82rem;font-weight:600;width:fit-content;max-width:calc(100% - 3rem);font-family:inherit;';

    var link = document.createElement('a');
    link.href = 'free-signals.html';
    link.style.cssText = 'color:inherit;text-decoration:none;flex:1;';
    link.textContent = '🔔 ' + t('search_reminder_text', 'Subscribe to daily signals to get notified first');

    var closeBtn = document.createElement('button');
    closeBtn.type = 'button';
    closeBtn.setAttribute('aria-label', 'close');
    closeBtn.textContent = '×';
    closeBtn.style.cssText = 'background:none;border:none;color:inherit;font-size:1rem;cursor:pointer;' +
      'line-height:1;padding:0 2px;font-family:inherit;flex-shrink:0;';
    closeBtn.onclick = function (e) {
      e.preventDefault();
      removeBanner();
    };

    bar.appendChild(link);
    bar.appendChild(closeBtn);
    return bar;
  }

  function removeBanner() {
    var el = document.getElementById('xflSearchReminder');
    if (el && el.parentNode) el.parentNode.removeChild(el);
  }

  function showBanner() {
    if (document.getElementById('xflSearchReminder')) return; // already showing
    var nav = document.querySelector('nav');
    var banner = buildBanner();
    if (nav && nav.parentNode) {
      nav.parentNode.insertBefore(banner, nav.nextSibling);
    } else {
      document.body.insertBefore(banner, document.body.firstChild);
    }
  }

  function wrapTracker() {
    var original = window.trackEvent;
    window.trackEvent = function (event_type, event_data) {
      if (event_type === 'search') {
        try { showBanner(); } catch (e) {}
      }
      return original ? original.apply(this, arguments) : undefined;
    };
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', wrapTracker);
  } else {
    wrapTracker();
  }
})();
