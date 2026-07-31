/* 2026-07-31 (monetization batch, task #599): neutral "explore brokers"
   panel shown under analysis results. Deliberately NOT tied to any
   specific BUY/SELL signal or ticker -- same "no trading signals" posture
   as js/decision-footer.js's 2026-07-30 Paddle-compliance rewrite (real
   support/resistance levels shown descriptively, never as "buy here").
   This widget renders NOTHING until at least one broker in
   services/broker_affiliate_config.py has a real affiliate_url configured
   -- see that file's docstring. Fully i18n-aware and carries an explicit
   affiliate disclosure (broker_cta_disclosure), same "never hide the
   commission" posture as every other monetization surface on this site. */
!function () {
  var styleInjected = false;
  var API_BASE = (window.XFINLAB_API_BASE || '');

  function injectStyle() {
    if (styleInjected) return;
    styleInjected = true;
    var css = ''
      + '.xfl-broker-cta{background:var(--bg-card,#fff);border:1px solid var(--border-color,#E5E7EB);border-radius:14px;padding:1.25rem 1.5rem;margin:1.2rem 0;font-family:"Inter",sans-serif}'
      + '.xfl-broker-cta-head{font-size:0.78rem;font-weight:700;letter-spacing:.04em;text-transform:uppercase;color:var(--accent-blue,#2563EB);margin-bottom:0.6rem}'
      + '.xfl-broker-cta-list{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:0.75rem;margin-bottom:0.7rem}'
      + '.xfl-broker-cta-item{border:1px solid var(--border-color,#E5E7EB);border-radius:10px;padding:0.75rem 0.9rem;background:var(--bg-secondary,#F8FAFC)}'
      + '.xfl-broker-cta-name{font-weight:700;font-size:0.92rem;color:var(--text-primary,#111);margin-bottom:0.25rem}'
      + '.xfl-broker-cta-desc{font-size:0.8rem;color:var(--text-secondary,#333);line-height:1.4;margin-bottom:0.6rem}'
      + '.xfl-broker-cta-link{display:inline-block;font-size:0.8rem;font-weight:600;color:#fff;background:var(--accent-blue,#2563EB);padding:0.35rem 0.8rem;border-radius:8px;text-decoration:none}'
      + '.xfl-broker-cta-disclosure{font-size:0.72rem;color:var(--text-muted,#666);line-height:1.4}';
    var el = document.createElement('style');
    el.textContent = css;
    document.head.appendChild(el);
  }

  function tr(key, fallback) {
    return (typeof I18N !== 'undefined' && I18N.translations && I18N.translations[key]) || fallback;
  }

  function render(container, brokers) {
    if (!brokers || !brokers.length) {
      container.innerHTML = '';
      return;
    }
    injectStyle();
    var html = '<div class="xfl-broker-cta">';
    html += '<div class="xfl-broker-cta-head">' + tr('broker_cta_title', 'Continue Your Research') + '</div>';
    html += '<div class="xfl-broker-cta-list">';
    brokers.forEach(function (b) {
      html += '<div class="xfl-broker-cta-item">'
        + '<div class="xfl-broker-cta-name">' + b.name + '</div>'
        + '<div class="xfl-broker-cta-desc">' + b.description + '</div>'
        + '<a class="xfl-broker-cta-link" href="' + b.url + '" target="_blank" rel="noopener sponsored">'
        + tr('broker_cta_learn_more', 'Learn More') + '</a>'
        + '</div>';
    });
    html += '</div>';
    html += '<div class="xfl-broker-cta-disclosure">' + tr('broker_cta_disclosure',
      'We may earn a commission if you open an account through these links, at no extra cost to you. This is not investment advice.') + '</div>';
    html += '</div>';
    container.innerHTML = html;
  }

  window.renderBrokerCta = function (containerIdOrEl, opts) {
    try {
      var container = typeof containerIdOrEl === 'string'
        ? document.getElementById(containerIdOrEl)
        : containerIdOrEl;
      if (!container) return;

      opts = opts || {};
      var url = API_BASE + '/api/broker-affiliates' + (opts.region ? ('?region=' + encodeURIComponent(opts.region)) : '');

      fetch(url).then(function (r) { return r.ok ? r.json() : { brokers: [] }; })
        .then(function (data) { render(container, data.brokers); })
        .catch(function () { container.innerHTML = ''; });
    } catch (e) {
      // never let this widget break the page around it
    }
  };
}();
