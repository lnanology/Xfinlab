// XFINLAB Nav Enhancement - adds login/user button only
(function() {
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
})();
