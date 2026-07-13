// XFINLAB site-wide Share widget -- floating button + platform picker,
// visible to every visitor (including anonymous), on every page that
// includes this script. Self-contained like js/theme-toggle.js: just
// drop <script src="js/share-widget.js"></script> anywhere and it works.
// Shares the site's general homepage link (no referral/tracking system --
// that's a separate, ticker-specific mechanism already on dashboard.html's
// "Share XFINLAB" modal).
(function () {
  var SITE_URL = 'https://www.xfinlab.com/';

  function t(key, fallback) {
    return (typeof I18N !== 'undefined' && I18N.translations && I18N.translations[key]) || fallback;
  }

  function shareCaption() {
    return t('share_caption', 'XFINLAB — Institutional-grade AI Investment Research. Analyze Stocks, ETFs & Crypto for free.');
  }

  function platformUrl(key) {
    var url = encodeURIComponent(SITE_URL);
    var text = encodeURIComponent(shareCaption());
    switch (key) {
      case 'whatsapp': return 'https://wa.me/?text=' + text + '%20' + url;
      case 'telegram': return 'https://t.me/share/url?url=' + url + '&text=' + text;
      case 'facebook': return 'https://www.facebook.com/sharer/sharer.php?u=' + url;
      case 'twitter': return 'https://twitter.com/intent/tweet?url=' + url + '&text=' + text;
      case 'linkedin': return 'https://www.linkedin.com/sharing/share-offsite/?url=' + url;
      case 'line': return 'https://social-plugins.line.me/lineit/share?url=' + url + '&text=' + text;
      default: return '#';
    }
  }

  var PLATFORMS = [
    {key: 'whatsapp', icon: '💬', label: 'WhatsApp'},
    {key: 'telegram', icon: '✈️', label: 'Telegram'},
    {key: 'facebook', icon: '📘', label: 'Facebook'},
    {key: 'twitter', icon: '✖️', label: 'X (Twitter)'},
    {key: 'linkedin', icon: '💼', label: 'LinkedIn'},
    {key: 'line', icon: '🟢', label: 'LINE'}
  ];

  function copyLink(itemEl) {
    var done = function () {
      var original = t('share_copy_link', 'Copy Link');
      itemEl.querySelector('span.share-item-label').textContent = t('share_copied', 'Copied!');
      setTimeout(function () {
        itemEl.querySelector('span.share-item-label').textContent = original;
      }, 1500);
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(SITE_URL).then(done).catch(function () {});
    } else {
      try {
        var ta = document.createElement('textarea');
        ta.value = SITE_URL;
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
        done();
      } catch (e) {}
    }
  }

  function buildItem(html, onClick, href) {
    var el = document.createElement(href ? 'a' : 'div');
    if (href) { el.href = href; el.target = '_blank'; el.rel = 'noopener'; }
    el.style.cssText = 'display:flex;align-items:center;gap:8px;padding:9px 14px;color:#e2e8f0;text-decoration:none;font-size:0.82rem;cursor:pointer;';
    el.innerHTML = html;
    el.onmouseenter = function () { el.style.background = '#111d30'; };
    el.onmouseleave = function () { el.style.background = 'transparent'; };
    if (onClick) el.onclick = function (e) { onClick(el, e); };
    return el;
  }

  function buildWidget() {
    if (document.getElementById('shareWidgetBtn')) return;

    var wrap = document.createElement('div');
    wrap.id = 'shareWidget';
    wrap.style.cssText = 'position:fixed;bottom:140px;right:24px;z-index:9996;';

    var panel = document.createElement('div');
    panel.id = 'sharePanel';
    panel.style.cssText = 'display:none;position:absolute;bottom:44px;right:0;background:#0d1525;border:1px solid #1e2d45;border-radius:10px;width:210px;box-shadow:0 8px 24px rgba(0,0,0,0.5);overflow:hidden;';

    var header = document.createElement('div');
    header.id = 'sharePanelTitle';
    header.style.cssText = 'padding:10px 14px;border-bottom:1px solid #1e2d45;font-size:0.68rem;font-weight:600;letter-spacing:0.1em;text-transform:uppercase;color:#64748b';
    header.textContent = t('share_panel_title', 'Share XFINLAB');
    panel.appendChild(header);

    PLATFORMS.forEach(function (p) {
      panel.appendChild(buildItem(
        '<span>' + p.icon + '</span><span class="share-item-label">' + p.label + '</span>',
        null,
        platformUrl(p.key)
      ));
    });

    var copyItem = buildItem(
      '<span>🔗</span><span class="share-item-label">' + t('share_copy_link', 'Copy Link') + '</span>',
      copyLink
    );
    copyItem.style.borderTop = '1px solid #1e2d45';
    panel.appendChild(copyItem);

    var btn = document.createElement('button');
    btn.id = 'shareWidgetBtn';
    btn.type = 'button';
    btn.style.cssText = 'background:#0d1525;border:1px solid #1e2d45;color:#e2e8f0;padding:8px 14px;border-radius:8px;cursor:pointer;font-size:0.82rem;white-space:nowrap;box-shadow:0 2px 8px rgba(0,0,0,0.3);font-family:inherit;';
    btn.textContent = '📤 ' + t('share_btn_label', 'Share');
    btn.onclick = function (e) {
      e.stopPropagation();
      panel.style.display = panel.style.display === 'block' ? 'none' : 'block';
    };

    document.addEventListener('click', function (e) {
      if (!wrap.contains(e.target)) panel.style.display = 'none';
    });

    wrap.appendChild(panel);
    wrap.appendChild(btn);
    document.body.appendChild(wrap);
  }

  // Re-apply translated labels once js/i18n.js finishes fetching
  // translations (it dispatches this event after apply() -- see
  // js/i18n.js). Harmless no-op if the widget hasn't been built yet.
  document.addEventListener('i18nApplied', function () {
    var btn = document.getElementById('shareWidgetBtn');
    if (btn) btn.textContent = '📤 ' + t('share_btn_label', 'Share');
    var title = document.getElementById('sharePanelTitle');
    if (title) title.textContent = t('share_panel_title', 'Share XFINLAB');
  });

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', buildWidget);
  } else {
    buildWidget();
  }
})();
