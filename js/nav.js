// XFINLAB Nav Enhancement - adds login/user button + site-wide analytics tracking
(function() {
  const API = 'https://api.xfinlab.com/api';
  const SESSION_ID = Math.random().toString(36).substring(2);

  // Global tracker so any page can call trackEvent('search', {ticker}) etc.
  // without redefining it. Fire-and-forget, never throws. Was previously
  // only defined inline on dashboard.html/chart-analysis.html, so every
  // other page (screener/stress-lab/company-compare/news/ai-analysis) was
  // invisible in the admin dashboard's DAU/MAU/trending stats.
  if (!window.trackEvent) {
    window.trackEvent = async function(event_type, event_data = null) {
      try {
        const token = localStorage.getItem('xfinlab_token');
        await fetch(`${API}/analytics/track`, {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({
            event_type,
            event_data,
            token,
            session_id: SESSION_ID,
            page: (location.pathname.split('/').pop() || 'index.html')
          })
        });
      } catch (e) {}
    };
  }

  function enhanceNav() {
    const user = JSON.parse(localStorage.getItem('xfinlab_user') || '{}');
    const nav = document.querySelector('nav');
    if (!nav) return;

    // 更新所有 logo 連結去 index.html
    const logos = nav.querySelectorAll('a.logo, a.nav-brand, a[class*="brand"]');
    logos.forEach(l => { l.href = 'index.html'; });

    // 加登入/用戶按鈕如果未有
    const hasAuth = nav.querySelector('a[href="login.html"], a[href="dashboard.html"]');
    if (!hasAuth) {
      const navRight = nav.querySelector('.nav-right') || nav.querySelector('.nav-links');
      if (navRight) {
        const btn = document.createElement('a');
        btn.href = user.name ? 'dashboard.html' : 'login.html';
        btn.textContent = user.name ? user.name.split(' ')[0] : '登入';
        btn.className = 'nav-cta';
        btn.style.cssText = 'background:#00d4ff;color:#000;padding:6px 14px;border-radius:6px;font-weight:600;font-size:0.82rem;text-decoration:none;margin-left:8px';
        navRight.appendChild(btn);
      }
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', enhanceNav);
  } else {
    enhanceNav();
  }

  // Auto page_view. Harmless if a page also fires its own (e.g.
  // dashboard.html, chart-analysis.html already do) -- DAU/MAU count
  // DISTINCT users per day, not raw event rows, so a duplicate page_view
  // doesn't skew those numbers.
  window.trackEvent('page_view', {page: (location.pathname.split('/').pop() || 'index.html')});
})();
