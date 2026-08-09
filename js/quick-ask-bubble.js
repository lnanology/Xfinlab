/*
 * 2026-08-09 (task #725, AJ "全做" batch): floating quick-ask chat bubble
 * with FAQ suggestions, modelled on the reference screenshots AJ shared of
 * Longbridge OpenAPI's docs site (floating chat icon -> large side panel
 * with "Guess you want to ask" suggested questions + a free-text input).
 *
 * This does NOT duplicate chat.html -- clicking a suggestion or submitting
 * the free-text box both hand off to chat.html?q=... (same mechanism
 * index.html's own hero "問AI" box and various "唔明？直接問AI" links
 * already use across the site), so there's one real chat implementation,
 * this is just a low-friction entry point into it from anywhere.
 *
 * Suggested questions reuse the homepage FAQ's existing faq1_q..faq7_q
 * i18n keys (already translated to 47 languages) instead of introducing
 * new duplicate copy -- only the bubble's own chrome (title/placeholder/
 * send button/"popular questions" label) needed new keys (qab_*).
 *
 * Positioned bottom-right, separate from the 6-item TG/feedback/share/
 * points/free-signals/language dock (js/mobile-widget-dock.js) rather than
 * folded into it -- that dock's grid is tuned for exactly 6 equal columns
 * (mobile 3x2, desktop 1x6); adding a 7th item would require re-deriving
 * that whole layout. Bottom offsets below are chosen to clear the dock in
 * both its mobile (edge-to-edge bottom bar) and desktop (centered pill,
 * bottom:20px) layouts.
 */
(function () {
  var FAQ_KEYS = ['faq1_q', 'faq2_q', 'faq3_q', 'faq4_q', 'faq5_q'];
  var STYLE_ID = 'xflQabStyle';

  function t(key, fallback) {
    if (typeof window.t === 'function') return window.t(key, fallback);
    return fallback;
  }

  function ensureStyle() {
    if (document.getElementById(STYLE_ID)) return;
    var css =
      '#xflQabBtn{position:fixed;right:20px;bottom:96px;z-index:1002;width:52px;height:52px;' +
        'border-radius:50%;background:var(--accent);color:#fff;border:none;cursor:pointer;' +
        'box-shadow:0 6px 20px rgba(var(--accent-rgb),0.4);display:flex;align-items:center;' +
        'justify-content:center;transition:transform 0.15s}' +
      '#xflQabBtn:hover{transform:scale(1.08)}' +
      '#xflQabPanel{position:fixed;right:20px;bottom:158px;z-index:1002;width:min(340px,88vw);' +
        'max-height:min(480px,70vh);background:var(--surface,#fff);border:1px solid var(--border,#e2e8f0);' +
        'border-radius:16px;box-shadow:0 12px 40px rgba(0,0,0,0.2);display:none;flex-direction:column;overflow:hidden}' +
      '#xflQabPanel.open{display:flex}' +
      '#xflQabHead{padding:14px 16px;background:var(--accent);color:#fff;display:flex;' +
        'justify-content:space-between;align-items:center;font-weight:700;font-size:0.92rem}' +
      '#xflQabClose{background:none;border:none;color:#fff;font-size:1.1rem;cursor:pointer;line-height:1}' +
      '#xflQabSuggestLabel{padding:12px 16px 4px;font-size:0.72rem;color:var(--muted,#64748b);' +
        'text-transform:uppercase;letter-spacing:0.04em}' +
      '#xflQabSuggestions{padding:4px 12px 8px;overflow-y:auto;flex:1}' +
      '.xfl-qab-chip{display:block;width:100%;text-align:left;background:var(--surface2,#f1f5f9);' +
        'border:1px solid var(--border,#e2e8f0);color:var(--text,#0f172a);border-radius:10px;' +
        'padding:9px 12px;margin-bottom:6px;font-size:0.82rem;cursor:pointer;transition:border-color 0.15s}' +
      '.xfl-qab-chip:hover{border-color:var(--accent)}' +
      '#xflQabInputRow{display:flex;gap:8px;padding:10px 12px;border-top:1px solid var(--border,#e2e8f0)}' +
      '#xflQabInput{flex:1;background:var(--surface2,#f1f5f9);border:1px solid var(--border,#e2e8f0);' +
        'color:var(--text,#0f172a);border-radius:8px;padding:8px 10px;font-size:0.82rem}' +
      '#xflQabSend{background:var(--accent);color:#fff;border:none;border-radius:8px;padding:8px 14px;' +
        'font-weight:600;font-size:0.82rem;cursor:pointer;white-space:nowrap}' +
      '@media (max-width:768px){#xflQabBtn{bottom:104px}#xflQabPanel{bottom:166px}}';
    var style = document.createElement('style');
    style.id = STYLE_ID;
    style.textContent = css;
    document.head.appendChild(style);
  }

  function goAsk(q) {
    q = (q || '').trim();
    if (!q) return;
    window.location.href = 'chat.html?q=' + encodeURIComponent(q);
  }

  function build() {
    ensureStyle();
    if (document.getElementById('xflQabBtn')) return;

    var btn = document.createElement('button');
    btn.id = 'xflQabBtn';
    btn.setAttribute('aria-label', t('qab_title', 'Ask Us Anything'));
    btn.innerHTML = '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/></svg>';

    var panel = document.createElement('div');
    panel.id = 'xflQabPanel';

    var suggestHtml = FAQ_KEYS.map(function (k) {
      var q = t(k, '');
      if (!q) return '';
      return '<button class="xfl-qab-chip" data-q="' + q.replace(/"/g, '&quot;') + '">' + q + '</button>';
    }).join('');

    panel.innerHTML =
      '<div id="xflQabHead"><span>' + t('qab_title', 'Ask Us Anything') + '</span>' +
      '<button id="xflQabClose" aria-label="close">✕</button></div>' +
      '<div id="xflQabSuggestLabel">' + t('qab_popular_label', 'Popular questions') + '</div>' +
      '<div id="xflQabSuggestions">' + suggestHtml + '</div>' +
      '<div id="xflQabInputRow">' +
      '<input id="xflQabInput" type="text" placeholder="' + t('qab_placeholder', 'Type your question...').replace(/"/g, '&quot;') + '">' +
      '<button id="xflQabSend">' + t('qab_send', 'Send') + '</button>' +
      '</div>';

    document.body.appendChild(btn);
    document.body.appendChild(panel);

    btn.addEventListener('click', function () {
      panel.classList.toggle('open');
    });
    panel.querySelector('#xflQabClose').addEventListener('click', function () {
      panel.classList.remove('open');
    });
    panel.querySelector('#xflQabSend').addEventListener('click', function () {
      goAsk(document.getElementById('xflQabInput').value);
    });
    panel.querySelector('#xflQabInput').addEventListener('keydown', function (e) {
      if (e.key === 'Enter') goAsk(this.value);
    });
    panel.querySelectorAll('.xfl-qab-chip').forEach(function (chip) {
      chip.addEventListener('click', function () {
        goAsk(chip.getAttribute('data-q'));
      });
    });
    document.addEventListener('click', function (e) {
      if (!panel.contains(e.target) && e.target !== btn && !btn.contains(e.target)) {
        panel.classList.remove('open');
      }
    });
  }

  function init() {
    // i18n.js populates window.t asynchronously (waits on a translations
    // fetch) -- same race every other widget on this site handles by just
    // deferring slightly rather than blocking page load on it.
    setTimeout(build, 300);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
