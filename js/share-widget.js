!function(){
  // 2026-07-31 fix ("分享功能自動帶referal link 及 QR code 給新用戶"):
  // this widget used to always share the bare homepage URL
  // (DEFAULT_URL below) for every visitor, logged in or not -- so a
  // logged-in user sharing XFINLAB got zero referral credit for anyone
  // who signed up through their share. Now, if the visitor is logged in
  // (xfinlab_token in localStorage, same key every other shared widget
  // on the site already uses -- see js/points-badge.js), this fetches
  // their personal referral link from the SAME /api/referral/code
  // endpoint dashboard.html's "Copy Referral Link" menu item already
  // uses (services/referral_service.py's ReferralService.get_stats(),
  // format "https://www.xfinlab.com/login.html?ref={code}") and uses
  // THAT as the share URL + QR code payload instead. Logged-out
  // visitors and any fetch failure fall back to the original bare
  // homepage URL unchanged -- this never blocks or breaks sharing.
  var DEFAULT_URL = "https://www.xfinlab.com/";
  var shareUrl = DEFAULT_URL;

  function t(key, fallback) {
    return (typeof I18N !== "undefined" && I18N.translations && I18N.translations[key]) || fallback;
  }

  function loadReferralLink() {
    try {
      var token = localStorage.getItem("xfinlab_token");
      if (!token) return;
      fetch("https://api.xfinlab.com/api/referral/code?token=" + encodeURIComponent(token))
        .then(function (res) { return res.ok ? res.json() : null; })
        .then(function (data) {
          if (data && data.referral_link) shareUrl = data.referral_link;
        })
        .catch(function () { /* keep DEFAULT_URL fallback */ });
    } catch (e) { /* localStorage unavailable -- keep DEFAULT_URL fallback */ }
  }

  function shareLinkFor(network) {
    var url = encodeURIComponent(shareUrl);
    var caption = encodeURIComponent(t("share_caption", "XFINLAB — Institutional-grade AI Investment Research. Analyze Stocks, ETFs & Crypto for free."));
    switch (network) {
      case "whatsapp": return "https://wa.me/?text=" + caption + "%20" + url;
      case "telegram": return "https://t.me/share/url?url=" + url + "&text=" + caption;
      case "facebook": return "https://www.facebook.com/sharer/sharer.php?u=" + url;
      case "twitter": return "https://twitter.com/intent/tweet?url=" + url + "&text=" + caption;
      case "linkedin": return "https://www.linkedin.com/sharing/share-offsite/?url=" + url;
      case "line": return "https://social-plugins.line.me/lineit/share?url=" + url + "&text=" + caption;
      default: return "#";
    }
  }

  var NETWORKS = [
    { key: "whatsapp", icon: "fa-brands fa-whatsapp", color: "#25D366", label: "WhatsApp" },
    { key: "telegram", icon: "fa-brands fa-telegram", color: "#26A5E4", label: "Telegram" },
    { key: "facebook", icon: "fa-brands fa-facebook", color: "#1877F2", label: "Facebook" },
    { key: "twitter", icon: "fa-brands fa-x-twitter", color: "var(--text-primary,#000000)", label: "X (Twitter)" },
    { key: "linkedin", icon: "fa-brands fa-linkedin", color: "#0A66C2", label: "LinkedIn" },
    { key: "line", icon: "fa-brands fa-line", color: "#00B900", label: "LINE" },
  ];

  function copyLink(item) {
    var restore = function () {
      var label = t("share_copy_link", "Copy Link");
      item.querySelector("span.share-item-label").textContent = t("share_copied", "Copied!");
      setTimeout(function () {
        item.querySelector("span.share-item-label").textContent = label;
      }, 1500);
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(shareUrl).then(restore).catch(function () {});
    } else {
      try {
        var ta = document.createElement("textarea");
        ta.value = shareUrl;
        document.body.appendChild(ta);
        ta.select();
        document.execCommand("copy");
        document.body.removeChild(ta);
        restore();
      } catch (e) {}
    }
  }

  function makeItem(innerHtml, onClick, href) {
    var el = document.createElement(href ? "a" : "div");
    if (href) {
      el.href = href;
      el.target = "_blank";
      el.rel = "noopener";
    }
    el.style.cssText = "display:flex;align-items:center;gap:8px;padding:9px 14px;color:var(--text-primary,#000000);text-decoration:none;font-size:0.82rem;cursor:pointer;";
    el.innerHTML = innerHtml;
    el.onmouseenter = function () { el.style.background = "var(--bg-secondary,#F8FAFC)"; };
    el.onmouseleave = function () { el.style.background = "transparent"; };
    if (onClick) el.onclick = function (e) { onClick(el, e); };
    return el;
  }

  function ensureQrModal() {
    if (document.getElementById("shareQrModal")) return;
    var modal = document.createElement("div");
    modal.id = "shareQrModal";
    modal.style.cssText = "display:none;position:fixed;inset:0;background:rgba(0,0,0,0.6);z-index:9999;align-items:center;justify-content:center;";
    modal.onclick = function (e) { if (e.target === modal) toggleQrModal(false); };

    var card = document.createElement("div");
    card.style.cssText = "background:var(--bg-card,#FFFFFF);border:1px solid var(--border-color,#000000);border-radius:14px;padding:24px;max-width:280px;width:90%;text-align:center;box-shadow:0 12px 40px rgba(0,0,0,0.25);";

    var title = document.createElement("div");
    title.id = "shareQrModalTitle";
    title.style.cssText = "font-size:0.85rem;font-weight:600;color:var(--text-primary,#000000);margin-bottom:14px;";
    title.textContent = t("share_qr_scan", "Scan to visit XFINLAB");
    card.appendChild(title);

    var img = document.createElement("img");
    img.id = "shareQrModalImg";
    var size = 200;
    img.src = "https://api.qrserver.com/v1/create-qr-code/?size=" + size + "x" + size + "&data=" + encodeURIComponent(shareUrl);
    img.alt = "XFINLAB QR Code";
    img.width = 200;
    img.height = 200;
    img.style.cssText = "border-radius:8px;background:#fff;padding:8px;";
    card.appendChild(img);

    var linkText = document.createElement("div");
    linkText.id = "shareQrModalLinkText";
    linkText.style.cssText = "margin-top:14px;font-size:0.8rem;color:var(--text-muted,#666666);word-break:break-all;";
    linkText.textContent = shareUrl.replace(/\/$/, "");
    card.appendChild(linkText);

    var closeBtn = document.createElement("button");
    closeBtn.type = "button";
    closeBtn.id = "shareQrModalClose";
    closeBtn.textContent = t("share_qr_close", "Close");
    closeBtn.style.cssText = "margin-top:16px;background:var(--bg-secondary,#F8FAFC);border:1px solid var(--border-color,#000000);color:var(--text-primary,#000000);padding:8px 18px;border-radius:8px;cursor:pointer;font-size:0.82rem;font-family:inherit;";
    closeBtn.onclick = function () { toggleQrModal(false); };
    card.appendChild(closeBtn);

    modal.appendChild(card);
    document.body.appendChild(modal);
  }

  function toggleQrModal(force) {
    ensureQrModal();
    // Refresh the QR image + link text every time it's opened, in case
    // the referral link finished loading asynchronously after the modal
    // element was first created.
    var img = document.getElementById("shareQrModalImg");
    if (img) img.src = "https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=" + encodeURIComponent(shareUrl);
    var linkText = document.getElementById("shareQrModalLinkText");
    if (linkText) linkText.textContent = shareUrl.replace(/\/$/, "");

    var modal = document.getElementById("shareQrModal");
    var show = typeof force === "boolean" ? force : modal.style.display !== "flex";
    modal.style.display = show ? "flex" : "none";
    var panel = document.getElementById("sharePanel");
    if (show && panel) panel.style.display = "none";
  }

  function buildWidget() {
    if (document.getElementById("shareWidgetBtn")) return;

    if (!document.getElementById("shareWidgetFA")) {
      var faLink = document.createElement("link");
      faLink.id = "shareWidgetFA";
      faLink.rel = "stylesheet";
      faLink.href = "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.2/css/all.min.css";
      document.head.appendChild(faLink);
    }

    var wrap = document.createElement("div");
    wrap.id = "shareWidget";
    wrap.style.cssText = "position:fixed;bottom:192px;right:24px;z-index:9996;";

    var panel = document.createElement("div");
    panel.id = "sharePanel";
    panel.style.cssText = "display:none;position:absolute;bottom:44px;right:0;background:var(--bg-card,#FFFFFF);border:1px solid var(--border-color,#000000);border-radius:10px;width:210px;box-shadow:0 8px 24px rgba(0,0,0,0.2);overflow:hidden;";

    var panelTitle = document.createElement("div");
    panelTitle.id = "sharePanelTitle";
    panelTitle.style.cssText = "padding:10px 14px;border-bottom:1px solid var(--border-color,#000000);font-size:0.68rem;font-weight:600;letter-spacing:0.1em;text-transform:uppercase;color:var(--text-muted,#666666)";
    panelTitle.textContent = t("share_panel_title", "Share XFINLAB");
    panel.appendChild(panelTitle);

    NETWORKS.forEach(function (net) {
      panel.appendChild(makeItem(
        '<i class="' + net.icon + '" style="color:' + net.color + ';width:16px;text-align:center;font-size:0.95rem;"></i><span class="share-item-label">' + net.label + "</span>",
        null,
        shareLinkFor(net.key)
      ));
    });

    var qrItem = makeItem(
      '<i class="fa-solid fa-qrcode" style="color:var(--text-primary,#000000);width:16px;text-align:center;font-size:0.95rem;"></i><span class="share-item-label" id="shareQrLabel">' + t("share_qr_code", "QR Code") + "</span>",
      function () { toggleQrModal(); }
    );
    qrItem.style.borderTop = "1px solid var(--border-color,#000000)";
    panel.appendChild(qrItem);

    panel.appendChild(makeItem(
      '<span>🔗</span><span class="share-item-label">' + t("share_copy_link", "Copy Link") + "</span>",
      copyLink
    ));

    var btn = document.createElement("button");
    btn.id = "shareWidgetBtn";
    btn.type = "button";
    btn.style.cssText = "background:var(--bg-card,#FFFFFF);border:1px solid var(--border-color,#000000);color:var(--text-primary,#000000);padding:8px 14px;border-radius:8px;cursor:pointer;font-size:0.82rem;white-space:nowrap;box-shadow:0 2px 8px rgba(0,0,0,0.15);font-family:inherit;";
    btn.textContent = "📤 " + t("share_btn_label", "Share");
    btn.onclick = function (e) {
      e.stopPropagation();
      // Rebuild the network links each time the panel opens, so a
      // referral link that finished loading after the widget was first
      // built (async fetch) is picked up instead of being stuck with
      // whatever shareUrl was at build time.
      var anchors = panel.querySelectorAll("a[target=_blank]");
      NETWORKS.forEach(function (net, i) {
        if (anchors[i]) anchors[i].href = shareLinkFor(net.key);
      });
      panel.style.display = panel.style.display === "block" ? "none" : "block";
    };

    document.addEventListener("click", function (e) {
      if (!wrap.contains(e.target)) panel.style.display = "none";
    });

    wrap.appendChild(panel);
    wrap.appendChild(btn);
    document.body.appendChild(wrap);
  }

  document.addEventListener("i18nApplied", function () {
    var btn = document.getElementById("shareWidgetBtn");
    if (btn) btn.textContent = "📤 " + t("share_btn_label", "Share");
    var panelTitle = document.getElementById("sharePanelTitle");
    if (panelTitle) panelTitle.textContent = t("share_panel_title", "Share XFINLAB");
    var qrLabel = document.getElementById("shareQrLabel");
    if (qrLabel) qrLabel.textContent = t("share_qr_code", "QR Code");
    var qrModalTitle = document.getElementById("shareQrModalTitle");
    if (qrModalTitle) qrModalTitle.textContent = t("share_qr_scan", "Scan to visit XFINLAB");
    var qrModalClose = document.getElementById("shareQrModalClose");
    if (qrModalClose) qrModalClose.textContent = t("share_qr_close", "Close");
  });

  loadReferralLink();

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", buildWidget);
  } else {
    buildWidget();
  }
}();
