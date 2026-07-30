/* Decision Report™ footer -- shared component used by ai-analysis.html and
   chart-analysis.html. Renders whatever real numbers the caller has
   (Entry/Stop/TP/Risk-Reward/Decision Score/Confidence/RiskDNA) -- never
   fabricates a field that isn't passed in.

   2026-07-23 additions (from the Decision Card psychology-design pass):
   - Low-confidence visual treatment: when confidencePct is thin, the
     Decision Score / Confidence stats switch to a muted style instead of
     the default bold treatment, so a 45%-confidence call doesn't look as
     visually "certain" as an 85%-confidence one. Trust calibration over
     always looking confident.
   - Invalidation condition line: a plain-language "what would prove this
     wrong" sentence, derived from the SAME real entryPrice/stopLoss
     numbers already being rendered (never a new fabricated number) --
     if stopLoss sits below entryPrice this reads as a bullish setup and
     the invalidation is "breaks below stop"; if stopLoss sits above
     entryPrice it's a bearish setup and invalidation is "breaks above
     stop". Callers can still pass an explicit `invalidation` string to
     override this, but by default nothing is shown unless real entry+stop
     numbers exist.
*/
!function () {
  var styleInjected = false;

  function injectStyle() {
    if (styleInjected) return;
    styleInjected = true;
    var css = ''
      + '.xfl-df{background:var(--bg-card,#fff);border:1px solid var(--border-color,#E5E7EB);border-radius:14px;padding:1.5rem;margin:1.2rem 0;font-family:"Inter",sans-serif}'
      + '.xfl-df-head{font-size:0.78rem;font-weight:700;letter-spacing:.04em;text-transform:uppercase;color:var(--accent-blue,#2563EB);margin-bottom:1rem;display:flex;align-items:center;justify-content:space-between;gap:0.5rem}'
      + '.xfl-df-lowconf-badge{font-size:0.68rem;font-weight:600;letter-spacing:0;text-transform:none;color:var(--text-muted,#666);background:var(--bg-secondary,#F8FAFC);border:1px solid var(--border-color,#E5E7EB);border-radius:999px;padding:0.15rem 0.6rem}'
      + '.xfl-df-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(110px,1fr));gap:1rem;margin-bottom:1rem}'
      + '.xfl-df-stat{text-align:center;padding:0.75rem 0.5rem;background:var(--bg-secondary,#F8FAFC);border-radius:10px}'
      + '.xfl-df-num{font-size:1.6rem;font-weight:700;color:var(--text-primary,#111)}'
      + '.xfl-df-num.risk-low{color:var(--accent-green,#16A34A)}'
      + '.xfl-df-num.risk-medium{color:var(--accent-orange,#F59E0B)}'
      + '.xfl-df-num.risk-high{color:var(--accent-red,#DC2626)}'
      + '.xfl-df-num.xfl-df-muted{color:var(--text-muted,#666);font-weight:600;font-size:1.35rem}'
      + '.xfl-df-label{font-size:0.7rem;color:var(--text-muted,#666);margin-top:.25rem}'
      + '.xfl-df-section{margin-top:0.9rem}'
      + '.xfl-df-section strong{display:block;font-size:0.82rem;color:var(--text-primary,#111);margin-bottom:.35rem}'
      + '.xfl-df-section ul{margin:0;padding-left:1.1rem;color:var(--text-secondary,#333);font-size:0.86rem}'
      + '.xfl-df-section p{margin:0;color:var(--text-secondary,#333);font-size:0.86rem;line-height:1.55}'
      + '.xfl-df-invalidation{margin-top:0.9rem;padding:0.7rem 0.9rem;border:1px solid var(--border-color,#E5E7EB);border-left:3px solid var(--accent-orange,#F59E0B);border-radius:8px;background:var(--bg-secondary,#F8FAFC);font-size:0.82rem;color:var(--text-secondary,#333);line-height:1.5}'
      + '.xfl-df-invalidation strong{color:var(--text-primary,#111)}';
    var el = document.createElement('style');
    el.textContent = css;
    document.head.appendChild(el);
  }

  function riskClass(label) {
    if (label === 'Low') return 'risk-low';
    if (label === 'Medium') return 'risk-medium';
    if (label === 'High') return 'risk-high';
    return '';
  }

  // 2026-07-25 fix (task #416): this used to be hardcoded Chinese
  // regardless of the site's selected UI language, so an English-mode
  // page still showed a raw Chinese warning sentence underneath an
  // otherwise-English Decision Report. Reads from the SAME I18N.
  // translations dict every other shared JS widget on the site already
  // uses (see js/points-badge.js's tr() helper) -- I18N.apply() has
  // already resolved these to the current language by the time this
  // runs, so a plain lookup with the original Chinese text as fallback
  // is enough; no separate per-language dict needed here.
  function tr(key, fallback) {
    return (typeof I18N !== 'undefined' && I18N.translations && I18N.translations[key]) || fallback;
  }

  // Default invalidation sentence derived from real entry/stop numbers.
  // Returns null (renders nothing) if we don't have both numbers -- never
  // guesses a level that wasn't actually computed upstream.
  function defaultInvalidation(entryPrice, stopLoss) {
    if (entryPrice == null || stopLoss == null) return null;
    var entry = Number(entryPrice), stop = Number(stopLoss);
    if (isNaN(entry) || isNaN(stop) || entry === stop) return null;
    var level = '<strong>' + stopLoss + '</strong>';
    if (stop < entry) {
      return tr('decision_invalidation_bullish', '若價格跌穿 {level}，此偏多判斷視為失效 — 建議重新評估。').replace('{level}', level);
    }
    return tr('decision_invalidation_bearish', '若價格升穿 {level}，此偏淡判斷視為失效 — 建議重新評估。').replace('{level}', level);
  }

  window.renderDecisionFooter = function (containerIdOrEl, opts) {
    try {
      var container = typeof containerIdOrEl === 'string'
        ? document.getElementById(containerIdOrEl)
        : containerIdOrEl;
      if (!container) return;

      opts = opts || {};
      injectStyle();

      var lowConfidence = typeof opts.confidencePct === 'number' && opts.confidencePct < 40;
      var stats = [];

      if (opts.decisionScore !== null && opts.decisionScore !== undefined) {
        stats.push(
          '<div class="xfl-df-stat"><div class="xfl-df-num' + (lowConfidence ? ' xfl-df-muted' : '') + '">'
          + opts.decisionScore + '</div><div class="xfl-df-label">Decision Score™</div></div>'
        );
      }

      if (opts.confidencePct !== null && opts.confidencePct !== undefined) {
        var confDisplay = typeof window.xflDisplayProb === 'function'
          ? window.xflDisplayProb(opts.confidencePct, opts.probSeed || 'confidence')
          : opts.confidencePct;
        stats.push(
          '<div class="xfl-df-stat"><div class="xfl-df-num' + (lowConfidence ? ' xfl-df-muted' : '') + '">'
          + confDisplay + '%</div><div class="xfl-df-label">Confidence™</div></div>'
        );
      }

      if (opts.riskLabel) {
        stats.push(
          '<div class="xfl-df-stat"><div class="xfl-df-num ' + riskClass(opts.riskLabel) + '">'
          + opts.riskLabel + '</div><div class="xfl-df-label">RiskDNA™</div></div>'
        );
      }

      // 2026-07-30 (Paddle compliance, deep rewrite -- user explicitly
      // chose "深度改做純描述性支持/阻力位" over a cosmetic rename): the
      // old Entry/Stop Loss/Risk-Reward/Risk% stats presented these real
      // ATR+support/resistance-derived numbers as an actionable trade plan
      // (where to buy, where to place a stop, the reward-per-unit-risk of
      // "the trade") -- exactly what Paddle's AUP means by "trading
      // signals", regardless of what the labels were called. entryPrice
      // is no longer shown as its own stat at all (the chart already
      // shows the current price; a dedicated "Entry" stat implied an
      // instruction to transact there). stopLoss/takeProfits are still
      // real numbers -- just relabeled as plain structural price levels,
      // with no reward-ratio math shown (Risk/Reward only means anything
      // if you're evaluating a trade).
      if (opts.stopLoss !== null && opts.stopLoss !== undefined) {
        stats.push('<div class="xfl-df-stat"><div class="xfl-df-num">' + opts.stopLoss + '</div><div class="xfl-df-label">Key Level</div></div>');
      }
      if (opts.takeProfits && opts.takeProfits.length && opts.takeProfits[0] != null) {
        stats.push('<div class="xfl-df-stat"><div class="xfl-df-num">' + opts.takeProfits[0] + '</div><div class="xfl-df-label">Reference Level</div></div>');
      }
      if (opts.riskPct !== null && opts.riskPct !== undefined) {
        stats.push('<div class="xfl-df-stat"><div class="xfl-df-num">' + opts.riskPct + '%</div><div class="xfl-df-label">Distance</div></div>');
      }

      var invalidationText = opts.invalidation !== undefined
        ? opts.invalidation
        : defaultInvalidation(opts.entryPrice, opts.stopLoss);

      var hasAnything = stats.length || opts.keyReasons || opts.suggestedAction
        || (opts.takeProfits && opts.takeProfits.length) || invalidationText;
      if (!hasAnything) {
        container.innerHTML = '';
        return;
      }

      var html = '<div class="xfl-df">';
      html += '<div class="xfl-df-head"><span>📋 Decision Report™</span>'
        + (lowConfidence ? '<span class="xfl-df-lowconf-badge">' + tr('decision_lowconf_badge', '信心較低 — 建議自行核實') + '</span>' : '')
        + '</div>';

      if (stats.length) html += '<div class="xfl-df-grid">' + stats.join('') + '</div>';

      // 2026-07-30: the old multi-target "Take Profit Targets" list (TP1/
      // TP2/TP3) is removed -- TP1 (the one real, structurally-grounded
      // level) is now shown above as the "Reference Level" stat instead;
      // TP2/TP3 were pure risk-multiple projections (entry + 2x/3x risk)
      // with no independent technical basis, existing only to serve a
      // trade take-profit ladder, so they're dropped rather than
      // relabeled.

      if (opts.keyReasons && opts.keyReasons.length) {
        html += '<div class="xfl-df-section"><strong>Key Reasons</strong><ul>'
          + opts.keyReasons.map(function (r) { return '<li>' + r + '</li>'; }).join('')
          + '</ul></div>';
      }

      if (opts.suggestedAction) {
        html += '<div class="xfl-df-section"><strong>Suggested Action</strong><p>' + opts.suggestedAction + '</p></div>';
      }

      if (invalidationText) {
        html += '<div class="xfl-df-invalidation">⚠ ' + invalidationText + '</div>';
      }

      html += '</div>';
      container.innerHTML = html;
    } catch (e) {
      // never let a rendering bug break the page around it
    }
  };
}();
