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

  // 用返每個平台自己嘅正式brand icon（Font Awesome brand set），唔再用
  // emoji將就。FA CSS用CDN動態加載一次，唔使逐個HTML檔案自己加<link>。
  var PLATFORMS = [
    {key: 'whatsapp', icon: 'fa-brands fa-whatsapp', color: '#25D366', label: 'WhatsApp'},
    {key: 'telegram', icon: 'fa-brands fa-telegram', color: '#26A5E4', label: 'Telegram'},
    {key: 'facebook', icon: 'fa-brands fa-facebook', color: '#1877F2', label: 'Facebook'},
    {key: 'twitter', icon: 'fa-brands fa-x-twitter', color: '#e2e8f0', label: 'X (Twitter)'},
    {key: 'linkedin', icon: 'fa-brands fa-linkedin', color: '#0A66C2', label: 'LinkedIn'},
    {key: 'line', icon: 'fa-brands fa-line', color: '#00B900', label: 'LINE'}
  ];

  function ensureFontAwesome() {
    if (document.getElementById('shareWidgetFA')) return;
    var link = document.createElement('link');
    link.id = 'shareWidgetFA';
    link.rel = 'stylesheet';
    link.href = 'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.2/css/all.min.css';
    document.head.appendChild(link);
  }

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

  // QR code image via qrserver.com's free, no-key-required API -- same
  // approach used elsewhere on the site for on-the-fly image generation
  // without adding a client-side QR library dependency.
  function qrImageUrl(size) {
    return 'https://api.qrserver.com/v1/create-qr-code/?size=' + size + 'x' + size + '&data=' + encodeURIComponent(SITE_URL);
  }

  function buildQrModal() {
    if (document.getElementById('shareQrModal')) return;

    var overlay = document.createElement('div');
    overlay.id = 'shareQrModal';
    overlay.style.cssText = 'display:none;position:fixed;inset:0;background:rgba(0,0,0,0.6);z-index:9999;align-items:center;justify-content:center;';
    overlay.onclick = function (e) { if (e.target === overlay) toggleQrModal(false); };

    var card = document.createElement('div');
    card.style.cssText = 'background:#0d1525;border:1px solid #1e2d45;border-radius:14px;padding:24px;max-width:280px;width:90%;text-align:center;box-shadow:0 12px 40px rgba(0,0,0,0.5);';

    var title = document.createElement('div');
    title.id = 'shareQrModalTitle';
    title.style.cssText = 'font-size:0.85rem;font-weight:600;color:#e2e8f0;margin-bottom:14px;';
    title.textContent = t('share_qr_scan', 'Scan to visit XFINLAB');
    card.appendChild(title);

    var img = document.createElement('img');
    img.src = qrImageUrl(200);
    img.alt = 'XFINLAB QR Code';
    img.width = 200;
    img.height = 200;
    img.style.cssText = 'border-radius:8px;background:#fff;padding:8px;';
    card.appendChild(img);

    var urlRow = document.createElement('div');
    urlRow.style.cssText = 'margin-top:14px;font-size:0.8rem;color:#94a3b8;word-break:break-all;';
    urlRow.textContent = SITE_URL.replace(/\/$/, '');
    card.appendChild(urlRow);

    var closeBtn = document.createElement('button');
    closeBtn.type = 'button';
    closeBtn.id = 'shareQrModalClose';
    closeBtn.textContent = t('share_qr_close', 'Close');
    closeBtn.style.cssText = 'margin-top:16px;background:#111d30;border:1px solid #1e2d45;color:#e2e8f0;padding:8px 18px;border-radius:8px;cursor:pointer;font-size:0.82rem;font-family:inherit;';
    closeBtn.onclick = function () { toggleQrModal(false); };
    card.appendChild(closeBtn);

    overlay.appendChild(card);
    document.body.appendChild(overlay);
  }

  function toggleQrModal(forceState) {
    buildQrModal();
    var overlay = document.getElementById('shareQrModal');
    var show = typeof forceState === 'boolean' ? forceState : overlay.style.display !== 'flex';
    overlay.style.display = show ? 'flex' : 'none';
    var panel = document.getElementById('sharePanel');
    if (show && panel) panel.style.display = 'none';
  }

  function buildWidget() {
    if (document.getElementById('shareWidgetBtn')) return;
    ensureFontAwesome();

    var wrap = document.createElement('div');
    wrap.id = 'shareWidget';
    // Right-side floating stack (bottom-up): TG Signals widget (24) ->
    // Daily Signals badge (80) -> language switcher (136) -> share
    // widget (192, here). Was bottom:140, bumped up to keep clear of
    // the language switcher's new position.
    wrap.style.cssText = 'position:fixed;bottom:192px;right:24px;z-index:9996;';

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
        '<i class="' + p.icon + '" style="color:' + p.color + ';width:16px;text-align:center;font-size:0.95rem;"></i><span class="share-item-label">' + p.label + '</span>',
        null,
        platformUrl(p.key)
      ));
    });

    var qrItem = buildItem(
      '<i class="fa-solid fa-qrcode" style="color:#e2e8f0;width:16px;text-align:center;font-size:0.95rem;"></i><span class="share-item-label" id="shareQrLabel">' + t('share_qr_code', 'QR Code') + '</span>',
      function () { toggleQrModal(); }
    );
    qrItem.style.borderTop = '1px solid #1e2d45';
    panel.appendChild(qrItem);

    var copyItem = buildItem(
      '<span>🔗</span><span class="share-item-label">' + t('share_copy_link', 'Copy Link') + '</span>',
      copyLink
    );
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
    var qrLabel = document.getElementById('shareQrLabel');
    if (qrLabel) qrLabel.textContent = t('share_qr_code', 'QR Code');
    var qrModalTitle = document.getElementById('shareQrModalTitle');
    if (qrModalTitle) qrModalTitle.textContent = t('share_qr_scan', 'Scan to visit XFINLAB');
    var qrModalClose = document.getElementById('shareQrModalClose');
    if (qrModalClose) qrModalClose.textContent = t('share_qr_close', 'Close');
  });

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', buildWidget);
  } else {
    buildWidget();
  }
})();
