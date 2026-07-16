/*
 * Points badge -- small pill shown just above the bottom-left Feedback
 * widget (js is inlined per-page, but they all share the same
 * #fbWidget fixed-position pattern at bottom:24px;left:24px).
 *
 * Backend: services/points_service.py -- every basic-feature use by a
 * logged-in FREE-plan user earns 1 point; reaching 500 points within a
 * rolling 7-day cycle grants a temporary 7-day Basic upgrade. Only
 * shown when logged in (localStorage 'xfinlab_token' present); silently
 * does nothing for guests or on any fetch failure.
 */
(function () {
  function ensureStyle() {
    if (document.getElementById('xfl-points-style')) return;
    var style = document.createElement('style');
    style.id = 'xfl-points-style';
    style.textContent =
      '#xflPointsBadge{position:fixed;bottom:80px;left:24px;z-index:998;' +
      'background:var(--surface,#0d1525);border:1px solid var(--border,#1e2d45);' +
      'border-radius:99px;padding:6px 14px;font-family:"Inter",sans-serif;' +
      'font-size:0.75rem;color:var(--text,#e2e8f0);box-shadow:0 4px 16px rgba(0,0,0,0.3);' +
      'display:none;white-space:nowrap}' +
      '#xflPointsBadge.xfl-boosted{color:var(--accent,#00d4ff);border-color:var(--accent,#00d4ff)}';
    document.head.appendChild(style);
  }

  function ensureBadge() {
    var el = document.getElementById('xflPointsBadge');
    if (el) return el;
    el = document.createElement('div');
    el.id = 'xflPointsBadge';
    document.body.appendChild(el);
    return el;
  }

  async function loadPointsBadge() {
    var token = null;
    try { token = localStorage.getItem('xfinlab_token'); } catch (e) {}
    if (!token) return;

    ensureStyle();
    var el = ensureBadge();

    try {
      var res = await fetch('https://api.xfinlab.com/api/points/status?token=' + encodeURIComponent(token));
      var data = await res.json();
      if (data.temp_plan) {
        var until = (data.temp_expires_at || '').split(' ')[0];
        el.textContent = '⭐ Basic 升級中 · ' + until;
        el.classList.add('xfl-boosted');
      } else if (data.points != null) {
        el.textContent = '🏅 ' + data.points + '/' + data.target + ' 積分';
        el.classList.remove('xfl-boosted');
      } else {
        return;
      }
      el.style.display = 'block';
    } catch (e) { /* silent -- never block the page */ }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', loadPointsBadge);
  } else {
    loadPointsBadge();
  }
  setInterval(loadPointsBadge, 5 * 60 * 1000);
})();
