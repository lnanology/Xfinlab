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

  // 已登入用戶專屬嘅Account flyout，加落所有include緊呢個nav.js嘅頁面
  // （index.html/dashboard.html已經有自己嘅版本，見下面判斷，唔會重複
  // 加多一個）。
  //
  // 2026-07-16修正(1)：呢度之前用position:fixed浮喺個page右上角，同好多
  // 功能頁自己個<nav>入面靠右嘅.nav-links撞位重疊。
  // 2026-07-16修正(2)：跟住試過插入做.nav-links嘅最後一個item，但呢8個
  // 功能頁本身已經有8-9個nav連結（Home/AI Analysis/Compare/News Denoise/
  // Stress Lab/Chart Analysis/Probability Scan/Anomaly Detection/Portfolio
  // Engine），加多一個落去同一行，喺標準桌面闊度已經好易迫爆行，令Account
  // 有時見到有時見唔到（睇瀏覽器閂幾闊）——用戶反映"都一至要有出現"。
  // 而家改做插入做<nav>本身嘅第三個flex item（同nav-brand、nav-links
  // 平級，唔係塞入.nav-links入面），並且畀番.nav-links自己
  // flex-shrink+overflow-x:auto（連結太多就自己刮唔係谷走Account），
  // Account個wrap就flex-shrink:0，靠瀏覽器flexbox本身保證佢永遠留喺
  // 最右邊、唔會俾其他連結谷到唔見。搵唔到<nav>本身（好罕有）先至
  // fallback做返fixed浮動。
  function injectUserTopbarFlyout() {
    const token = localStorage.getItem('xfinlab_token');
    if (!token) return;
    // index.html有自己個#userTopbar，dashboard.html有自己個#accountBtn
    // 帳戶選單，兩者都已經滿足到「Account」呢個需求，唔使再加。
    if (document.getElementById('userTopbar') || document.getElementById('accountBtn')) return;
    if (document.getElementById('xflSettingsWrap')) return;

    let user = {};
    try { user = JSON.parse(localStorage.getItem('xfinlab_user') || '{}'); } catch (e) {}

    const navLinksEl = document.querySelector('.nav-links') || document.querySelector('.nav-right');
    // 用返.nav-links/.nav-right自己所屬嗰個<nav>（closest），唔係盲搵
    // 成頁第一個<nav>標籤 -- 有啲頁面（例如chat.html）唔止得一個<nav>。
    const navEl = (navLinksEl && navLinksEl.closest('nav')) || document.querySelector('nav');
    const inFlow = !!navEl;

    const style = document.createElement('style');
    style.textContent = `
      #xflFloatTopbar{position:fixed;top:12px;right:16px;z-index:9997;display:flex;align-items:center;gap:8px;font-family:'Inter',sans-serif;}
      .xfl-settings-wrap{position:relative;display:inline-flex;align-items:center;flex-shrink:0;margin-left:12px;}
      .xfl-settings-btn{background:#0d1525;border:1px solid #1e2d45;color:#94a3b8;padding:6px 12px;border-radius:8px;font-size:0.8rem;cursor:pointer;font-family:inherit;transition:border-color .2s,color .2s;white-space:nowrap;}
      .xfl-settings-btn:hover{border-color:#00d4ff;color:#00d4ff;}
      .xfl-flyout{display:none;position:absolute;right:0;top:calc(100% + 6px);background:#0d1525;border:1px solid #1e2d45;border-radius:8px;min-width:220px;overflow:hidden;box-shadow:0 8px 24px rgba(0,0,0,0.4);z-index:200;}
      .xfl-settings-wrap:hover .xfl-flyout, .xfl-flyout.xfl-open{display:block;}
      .xfl-flyout a{display:block;padding:10px 14px;color:#e2e8f0;text-decoration:none;font-size:0.82rem;}
      .xfl-flyout a:hover{background:#131c2e;color:#00d4ff;}
      .xfl-flyout-head{padding:12px 16px;border-bottom:1px solid #1e2d45;}
      .xfl-flyout-head .xfl-email{font-size:0.82rem;color:#e2e8f0;margin-top:2px;word-break:break-all;}
      .xfl-flyout-head .xfl-signedin{font-size:0.72rem;color:#64748b;}
      .xfl-flyout-head .xfl-plan{font-size:0.7rem;color:#00d4ff;margin-top:2px;text-transform:uppercase;letter-spacing:0.08em;}
      /* 桌面版先至畀連結行自己刮，闊度唔夠嘅話 -- 手機版<=768px嗰個
         .nav-links已經變咗做position:absolute嘅落拉selu menu（見
         css/style.css嘅media query），呢度加嘅overflow-x規則對嗰個
         狀態冇影響。 */
      @media (min-width:769px){
        nav{flex-wrap:nowrap;}
        .nav-links{flex-shrink:1;min-width:0;overflow-x:auto;scrollbar-width:thin;}
        .nav-right{flex-shrink:1;min-width:0;overflow-x:auto;scrollbar-width:thin;}
      }
    `;
    document.head.appendChild(style);

    const wrap = document.createElement('div');
    wrap.className = 'xfl-settings-wrap';
    wrap.id = 'xflSettingsWrap';
    wrap.innerHTML = `
      <button type="button" class="xfl-settings-btn" id="xflSettingsBtn">👤 帳戶</button>
      <div class="xfl-flyout" id="xflFlyout">
        <div class="xfl-flyout-head">
          <div class="xfl-signedin" id="xflSignedInLabel">Signed in as</div>
          <div class="xfl-email">${user.email || ''}</div>
          <div class="xfl-plan">${(user.plan || 'free').toUpperCase()} <span id="xflPlanSuffix">PLAN</span></div>
        </div>
        <a href="#" id="xflReferralLink">🔗 <span id="xflReferralLabel">Copy Referral Link</span></a>
        <a href="#" id="xflShareLink">📤 <span id="xflShareLabel">Share XFINLAB</span></a>
        <a href="#" id="xflLogoutLink" style="color:#ef4444">↩ <span id="xflLogoutLabel">Sign Out</span></a>
      </div>
    `;

    if (inFlow) {
      // 插入做<nav>嘅直屬最後一個child（同nav-brand/nav-links平級），
      // 唔係塞入.nav-links入面 -- 咁樣先至唔會俾一大堆連結谷走。
      navEl.appendChild(wrap);
    } else {
      // Fallback：頁面完全搵唔到<nav>先至用返fixed浮動。
      const bar = document.createElement('div');
      bar.id = 'xflFloatTopbar';
      bar.appendChild(wrap);
      document.body.appendChild(bar);
    }

    const btn = document.getElementById('xflSettingsBtn');
    const flyout = document.getElementById('xflFlyout');
    btn.addEventListener('click', function(e) {
      e.stopPropagation();
      flyout.classList.toggle('xfl-open');
    });
    document.addEventListener('click', function() {
      flyout.classList.remove('xfl-open');
    });

    // 3個action，內容/行為同dashboard.html個accountBtn dropdown一致
    // （複製推薦連結/分享XFINLAB/登出）。
    document.getElementById('xflReferralLink').addEventListener('click', async function(e) {
      e.preventDefault();
      try {
        const res = await fetch(`${API}/referral/code?token=${token}`);
        const data = await res.json();
        navigator.clipboard.writeText(data.referral_link);
        const tpl = (typeof I18N !== 'undefined' && I18N.translations && I18N.translations['dash_alert_referral_copied']) || 'Referral link copied: {link}';
        alert(tpl.replace('{link}', data.referral_link));
      } catch (err) {
        alert((typeof I18N !== 'undefined' && I18N.translations && I18N.translations['dash_err_referral']) || 'Error getting referral link');
      }
    });
    document.getElementById('xflShareLink').addEventListener('click', function(e) {
      e.preventDefault();
      // 重用js/share-widget.js已經起好嗰個site-wide Share面板。
      const shareBtn = document.getElementById('shareWidgetBtn');
      if (shareBtn) { shareBtn.click(); return; }
      navigator.clipboard.writeText('https://www.xfinlab.com/');
    });
    document.getElementById('xflLogoutLink').addEventListener('click', function(e) {
      e.preventDefault();
      localStorage.removeItem('xfinlab_token');
      localStorage.removeItem('xfinlab_user');
      window.location.href = 'login.html';
    });

    // 如果個頁面有load i18n.js，跟返用戶語言顯示；未load到嘅話就keep
    // 住Chinese fallback（同index.html嗰個topbar一致嘅預設）。
    function applyTopbarI18n() {
      if (typeof I18N === 'undefined' || !I18N.translations) return;
      const tr = I18N.translations;
      if (tr['topbar_account']) btn.innerHTML = '👤 ' + tr['topbar_account'];
      if (tr['dash_signed_in_as']) document.getElementById('xflSignedInLabel').textContent = tr['dash_signed_in_as'];
      if (tr['dash_plan_suffix']) document.getElementById('xflPlanSuffix').textContent = tr['dash_plan_suffix'];
      if (tr['dash_menu_referral']) document.getElementById('xflReferralLabel').textContent = tr['dash_menu_referral'];
      if (tr['dash_menu_share']) document.getElementById('xflShareLabel').textContent = tr['dash_menu_share'];
      if (tr['dash_menu_signout']) document.getElementById('xflLogoutLabel').textContent = tr['dash_menu_signout'];
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
