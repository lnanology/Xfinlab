// XFINLAB cookie / local-storage consent banner (2026-07-20).
//
// Built after the user confirmed "yes, add it" to a cookie-consent
// banner request. Kept honest about what this site actually does --
// no third-party ad network or tracking pixel exists here (confirmed via
// grep before writing this: no Google Analytics/Meta Pixel/etc. anywhere
// in the codebase), so the banner text describes the REAL uses of
// localStorage on this site: auth token (js/*.html login flows),
// language/theme preference (js/i18n.js, js/theme-toggle.js), and
// first-party usage analytics (the trackEvent() calls already present in
// dashboard.html/chart-analysis.html, which POST to XFINLAB's own backend,
// never a third party). It never claims marketing/ad-tracking cookies
// that don't exist.
//
// "Decline" has real teeth, not just cosmetic: it sets
// window.XFLConsent.hasAnalyticsConsent() to false, and the two existing
// trackEvent() functions should (and, per the accompanying commit, now
// do) skip their fetch() call when that's false -- so declining actually
// stops the first-party analytics POSTs, not just hides the banner.
(function () {
  var STORAGE_KEY = 'xfl_cookie_consent'; // 'accepted' | 'declined'

  function t(key, fallback) {
    return (typeof I18N !== 'undefined' && I18N.translations && I18N.translations[key]) || fallback;
  }

  function getConsent() {
    try { return localStorage.getItem(STORAGE_KEY); } catch (e) { return null; }
  }

  function setConsent(value) {
    try { localStorage.setItem(STORAGE_KEY, value); } catch (e) {}
  }

  // Public hook other scripts can check before firing any first-party
  // analytics call. Defaults to true (allowed) until the user explicitly
  // declines -- this is lightweight first-party usage analytics posted to
  // XFINLAB's own backend, not third-party ad tracking, so an undecided
  // visitor isn't blocked from a normal experience while the banner is
  // still showing.
  window.XFLConsent = {
    hasAnalyticsConsent: function () {
      return getConsent() !== 'declined';
    },
    getStatus: function () {
      return getConsent();
    }
  };

  function ensureStyle() {
    if (document.getElementById('xfl-cookie-style')) return;
    var style = document.createElement('style');
    style.id = 'xfl-cookie-style';
    style.textContent =
      '#xflCookieBanner{position:fixed;left:0;right:0;bottom:0;z-index:10001;' +
      'background:var(--bg-card,#FFFFFF);border-top:1px solid var(--border-color,#000000);' +
      'box-shadow:0 -4px 20px rgba(0,0,0,0.12);padding:14px 20px;display:flex;flex-wrap:wrap;' +
      'align-items:center;gap:14px;font-family:inherit}' +
      '#xflCookieBanner .xfl-cookie-text{flex:1 1 320px;font-size:0.82rem;line-height:1.5;' +
      'color:var(--text-secondary,#333333)}' +
      '#xflCookieBanner .xfl-cookie-text a{color:var(--accent-blue,#2563EB);text-decoration:underline}' +
      '#xflCookieBanner .xfl-cookie-actions{display:flex;gap:10px;flex-shrink:0;flex-wrap:wrap}' +
      '#xflCookieAccept{background:var(--accent-blue,#2563EB);color:#fff;border:none;padding:9px 18px;' +
      'border-radius:8px;font-weight:700;font-size:0.82rem;cursor:pointer;white-space:nowrap;font-family:inherit}' +
      '#xflCookieDecline{background:none;border:1px solid var(--border-color,#000000);' +
      'color:var(--text-primary,#000000);padding:9px 18px;border-radius:8px;font-weight:600;' +
      'font-size:0.82rem;cursor:pointer;white-space:nowrap;font-family:inherit}' +
      '@media(max-width:520px){#xflCookieBanner{padding:12px 14px}}';
    document.head.appendChild(style);
  }

  function buildBanner() {
    var wrap = document.createElement('div');
    wrap.id = 'xflCookieBanner';

    var textEl = document.createElement('div');
    textEl.className = 'xfl-cookie-text';
    var learnMoreHref = 'privacy.html';
    textEl.innerHTML = '🍪 ' + t('cookie_banner_text', 'This site uses cookies and local storage to keep you signed in, remember your language/theme preferences, and anonymously analyze site usage to improve our service.') +
      ' <a href="' + learnMoreHref + '">' + t('cookie_learn_more', 'Learn more') + '</a>';

    var actions = document.createElement('div');
    actions.className = 'xfl-cookie-actions';

    var declineBtn = document.createElement('button');
    declineBtn.type = 'button';
    declineBtn.id = 'xflCookieDecline';
    declineBtn.textContent = t('cookie_decline_btn', 'Essential Only');
    declineBtn.onclick = function () {
      setConsent('declined');
      removeBanner();
    };

    var acceptBtn = document.createElement('button');
    acceptBtn.type = 'button';
    acceptBtn.id = 'xflCookieAccept';
    acceptBtn.textContent = t('cookie_accept_btn', 'Accept All Cookies');
    acceptBtn.onclick = function () {
      setConsent('accepted');
      removeBanner();
    };

    actions.appendChild(declineBtn);
    actions.appendChild(acceptBtn);
    wrap.appendChild(textEl);
    wrap.appendChild(actions);
    return wrap;
  }

  function removeBanner() {
    var el = document.getElementById('xflCookieBanner');
    if (el && el.parentNode) el.parentNode.removeChild(el);
    stopStackWatch();
  }

  // While the banner sits fixed at bottom:0, it visually covers the
  // bottom portion of the right-side floating widget stack (TG Signals
  // widget bottom:24 -> Daily Signals badge bottom:80 -> language
  // switcher bottom:136 -> share widget bottom:192 -- see the stack-order
  // comment in js/free-signals-badge.js). Push that whole stack up by the
  // banner's own rendered height (plus a small gap) for as long as the
  // banner is visible, using !important inline overrides so it beats each
  // widget's own inline bottom value. Reverted the moment the banner is
  // dismissed.
  var STACK_IDS = { tgWidget: 24, freeSignalsBadge: 80, langSwitcher: 136, shareWidget: 192 };
  var stackObserver = null;

  function applyStackOffset(offsetPx) {
    Object.keys(STACK_IDS).forEach(function (id) {
      var el = document.getElementById(id);
      if (el) el.style.setProperty('bottom', (STACK_IDS[id] + offsetPx) + 'px', 'important');
    });
  }

  function clearStackOffset() {
    Object.keys(STACK_IDS).forEach(function (id) {
      var el = document.getElementById(id);
      if (el) el.style.removeProperty('bottom');
    });
  }

  function startStackWatch(offsetPx) {
    applyStackOffset(offsetPx);
    if (stackObserver) return;
    // Some of these widgets (Daily Signals badge, language switcher,
    // share widget) are appended to <body> asynchronously on their own
    // DOMContentLoaded handlers, which may run after this one -- watch
    // for late arrivals and re-apply the offset to them too.
    stackObserver = new MutationObserver(function () { applyStackOffset(offsetPx); });
    stackObserver.observe(document.body, { childList: true });
  }

  function stopStackWatch() {
    if (stackObserver) { stackObserver.disconnect(); stackObserver = null; }
    clearStackOffset();
  }

  function init() {
    if (getConsent()) return; // already decided, don't show again
    ensureStyle();
    var banner = buildBanner();
    document.body.appendChild(banner);
    requestAnimationFrame(function () {
      startStackWatch(banner.offsetHeight + 8);
    });
    window.addEventListener('resize', function () {
      var el = document.getElementById('xflCookieBanner');
      if (el) startStackWatch(el.offsetHeight + 8);
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
