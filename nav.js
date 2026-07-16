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

  // 已登入用戶專屬嘅浮動Settings->Account flyout，加落所有include緊呢個
  // nav.js嘅頁面（index.html/dashboard.html已經有自己嘅版本，見下面
  // 判斷，唔會重複加多一個）。指住/撳落「⚙️ 設定」會滑出「👤 帳戶」
  // 呢個選項，用戶要求「所有頁面都要加」呢個功能，唔止主頁先有。
  function injectUserTopbarFlyout() {
    const user = JSON.parse(localStorage.getItem('xfinlab_user') || '{}');
    const token = localStorage.getItem('xfinlab_token');
    if (!token) return;
    // index.html有自己個#userTopbar，dashboard.html有自己個#accountBtn
    // 帳戶選單，兩者都已經滿足到「Settings/Account」呢個需求，唔使再加。
    if (document.getElementById('userTopbar') || document.getElementById('accountBtn')) return;
    if (document.getElementById('xflFloatTopbar')) return;

    const style = document.createElement('style');
    style.textContent = `
      #xflFloatTopbar{position:fixed;top:12px;right:16px;z-index:9997;display:flex;align-items:center;gap:8px;font-family:'Inter',sans-serif;}
      #xflFloatTopbar .xfl-name{font-size:0.78rem;color:#e2e8f0;background:#0d1525;border:1px solid #1e2d45;padding:6px 10px;border-radius:8px;white-space:nowrap;}
      .xfl-settings-wrap{position:relative;}
      .xfl-settings-btn{background:#0d1525;border:1px solid #1e2d45;color:#94a3b8;padding:6px 12px;border-radius:8px;font-size:0.8rem;cursor:pointer;font-family:inherit;transition:border-color .2s,color .2s;white-space:nowrap;}
      .xfl-settings-btn:hover{border-color:#00d4ff;color:#00d4ff;}
      .xfl-flyout{display:none;position:absolute;right:0;top:calc(100% + 6px);background:#0d1525;border:1px solid #1e2d45;border-radius:8px;min-width:140px;overflow:hidden;box-shadow:0 8px 24px rgba(0,0,0,0.4);}
      .xfl-settings-wrap:hover .xfl-flyout, .xfl-flyout.xfl-open{display:block;}
      .xfl-flyout a{display:block;padding:10px 14px;color:#e2e8f0;text-decoration:none;font-size:0.82rem;}
      .xfl-flyout a:hover{background:#131c2e;color:#00d4ff;}
      @media (max-width:640px){ #xflFloatTopbar{top:8px;right:8px;} #xflFloatTopbar .xfl-name{display:none;} }
    `;
    document.head.appendChild(style);

    const bar = document.createElement('div');
    bar.id = 'xflFloatTopbar';
    const firstName = user.name ? user.name.split(' ')[0] : '';
    bar.innerHTML = `
      <span class="xfl-name">👤 ${firstName}</span>
      <div class="xfl-settings-wrap" id="xflSettingsWrap">
        <button type="button" class="xfl-settings-btn" id="xflSettingsBtn">⚙️ 設定</button>
        <div class="xfl-flyout" id="xflFlyout">
          <a href="dashboard.html" id="xflAccountLink">👤 帳戶</a>
        </div>
      </div>
    `;
    document.body.appendChild(bar);

    const btn = document.getElementById('xflSettingsBtn');
    const flyout = document.getElementById('xflFlyout');
    btn.addEventListener('click', function(e) {
      e.stopPropagation();
      flyout.classList.toggle('xfl-open');
    });
    document.addEventListener('click', function() {
      flyout.classList.remove('xfl-open');
    });

    // 如果個頁面有load i18n.js，跟返用戶語言顯示；未load到嘅話就keep
    // 住Chinese fallback（同index.html嗰個topbar一致嘅預設）。
    function applyTopbarI18n() {
      if (typeof I18N === 'undefined' || !I18N.translations) return;
      const s = I18N.translations['topbar_settings'];
      const a = I18N.translations['topbar_account'];
      if (s) btn.textContent = s;
      if (a) document.getElementById('xflAccountLink').innerHTML = '👤 ' + a;
    }
    applyTopbarI18n();
    document.addEventListener('i18nApplied', applyTopbarI18n);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', enhanceNav);
    document.addEventListener('DOMContentLoaded', injectUserTopbarFlyout);
  } else {
    enhanceNav();
    injectUserTopbarFlyout();
  }

  // Auto page_view. Harmless if a page also fires its own (e.g.
  // dashboard.html, chart-analysis.html already do) -- DAU/MAU count
  // DISTINCT users per day, not raw event rows, so a duplicate page_view
  // doesn't skew those numbers.
  window.trackEvent('page_view', {page: (location.pathname.split('/').pop() || 'index.html')});
})();
