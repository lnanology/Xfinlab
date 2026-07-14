/*
 * Shared "Decision Report" footer -- the standardized closing block
 * required by brand principle #5: 所有分析結果都以 Decision Score(TM) +
 * Confidence(TM) + RiskDNA(TM) 作為統一輸出.
 *
 * IMPORTANT: this is only wired into pages that have a REAL numeric
 * composite score already computed server-side (ai-analysis.html,
 * chart-analysis.html). It is deliberately NOT added to every analysis
 * page:
 *   - news-denoise.html / company-compare.html / stress-lab.html return
 *     free-text AI analysis with no numeric composite score at all --
 *     forcing a Decision Score(TM) number here would mean inventing one,
 *     which this codebase has consistently avoided all session.
 *   - probability-scan.html (api/pipeline_api.py) has an explicit,
 *     documented design decision to NOT show recommendation-style
 *     language, because MasterPipeline's internal formulas are not
 *     backtested/calibrated ("唔應該扮專業投資建議" -- see that file's
 *     module docstring). Adding a "Suggested Action" there would
 *     contradict that.
 *   - screener.html shows a multi-ticker list, not a single closed-out
 *     report, so a single footer doesn't fit the shape of the page.
 *
 * Self-contained like js/ai-loading.js: injects its own CSS once, exposes
 * window.renderDecisionFooter(container, opts) which each page calls with
 * ONLY real fields it already has. Any field left out (null/undefined) is
 * simply omitted from the rendered card rather than shown as a fake value.
 *
 * opts:
 *   decisionScore   number 0-100 or null
 *   confidencePct   number 0-100 or null
 *   riskLabel       "Low" | "Medium" | "High" or null
 *   keyReasons      string[] or null
 *   suggestedAction string or null
 *
 *   -- Phase 1 Decision Engine upgrade (additive, all optional) --
 *   entryPrice      number or null (real last close, not a fabricated one)
 *   stopLoss        number or null
 *   takeProfits     number[] (TP1/TP2/TP3) or null
 *   riskReward      number or null (e.g. 1.45 -> rendered as "1:1.45")
 *   riskPct         number or null (distance to stop as % of entry)
 *   Only ever passed when services/technical_analysis_service.py's
 *   _decision_levels() actually produced real numbers from support/
 *   resistance/ATR -- never a guessed price. Absolute position sizing is
 *   deliberately not part of this footer at all (needs the user's account
 *   size/risk tolerance, which no page here has).
 */
(function () {
  var _styled = false;

  function _ensureStyle() {
    if (_styled) return;
    _styled = true;
    var style = document.createElement('style');
    style.textContent =
      '.xfl-df{background:var(--bg-card,#fff);border:1px solid var(--border-color,#E5E7EB);' +
      'border-radius:14px;padding:1.5rem;margin:1.2rem 0;font-family:"Inter",sans-serif}' +
      '.xfl-df-head{font-size:0.78rem;font-weight:700;letter-spacing:.04em;text-transform:uppercase;' +
      'color:var(--accent-blue,#2563EB);margin-bottom:1rem}' +
      '.xfl-df-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(110px,1fr));gap:1rem;' +
      'margin-bottom:1rem}' +
      '.xfl-df-stat{text-align:center;padding:0.75rem 0.5rem;background:var(--bg-secondary,#F8FAFC);' +
      'border-radius:10px}' +
      '.xfl-df-num{font-size:1.6rem;font-weight:700;color:var(--text-primary,#111)}' +
      '.xfl-df-num.risk-low{color:var(--accent-green,#16A34A)}' +
      '.xfl-df-num.risk-medium{color:var(--accent-orange,#F59E0B)}' +
      '.xfl-df-num.risk-high{color:var(--accent-red,#DC2626)}' +
      '.xfl-df-label{font-size:0.7rem;color:var(--text-muted,#666);margin-top:.25rem}' +
      '.xfl-df-section{margin-top:0.9rem}' +
      '.xfl-df-section strong{display:block;font-size:0.82rem;color:var(--text-primary,#111);' +
      'margin-bottom:.35rem}' +
      '.xfl-df-section ul{margin:0;padding-left:1.1rem;color:var(--text-secondary,#333);font-size:0.86rem}' +
      '.xfl-df-section p{margin:0;color:var(--text-secondary,#333);font-size:0.86rem;line-height:1.55}';
    document.head.appendChild(style);
  }

  function _riskClass(label) {
    if (label === 'Low') return 'risk-low';
    if (label === 'Medium') return 'risk-medium';
    if (label === 'High') return 'risk-high';
    return '';
  }

  function render(container, opts) {
    try {
      var el = typeof container === 'string' ? document.getElementById(container) : container;
      if (!el) return;
      opts = opts || {};
      _ensureStyle();

      var stats = [];
      if (opts.decisionScore !== null && opts.decisionScore !== undefined) {
        stats.push('<div class="xfl-df-stat"><div class="xfl-df-num">' +
          opts.decisionScore + '</div><div class="xfl-df-label">Decision Score™</div></div>');
      }
      if (opts.confidencePct !== null && opts.confidencePct !== undefined) {
        stats.push('<div class="xfl-df-stat"><div class="xfl-df-num">' +
          opts.confidencePct + '%</div><div class="xfl-df-label">Confidence™</div></div>');
      }
      if (opts.riskLabel) {
        stats.push('<div class="xfl-df-stat"><div class="xfl-df-num ' + _riskClass(opts.riskLabel) + '">' +
          opts.riskLabel + '</div><div class="xfl-df-label">RiskDNA™</div></div>');
      }

      // Phase 1 additions -- Entry/Stop/Risk-Reward/Risk% (all optional,
      // same omit-if-absent rule as everything else in this file).
      if (opts.entryPrice !== null && opts.entryPrice !== undefined) {
        stats.push('<div class="xfl-df-stat"><div class="xfl-df-num">' +
          opts.entryPrice + '</div><div class="xfl-df-label">Entry</div></div>');
      }
      if (opts.stopLoss !== null && opts.stopLoss !== undefined) {
        stats.push('<div class="xfl-df-stat"><div class="xfl-df-num">' +
          opts.stopLoss + '</div><div class="xfl-df-label">Stop Loss</div></div>');
      }
      if (opts.riskReward !== null && opts.riskReward !== undefined) {
        stats.push('<div class="xfl-df-stat"><div class="xfl-df-num">1:' +
          opts.riskReward + '</div><div class="xfl-df-label">Risk/Reward</div></div>');
      }
      if (opts.riskPct !== null && opts.riskPct !== undefined) {
        stats.push('<div class="xfl-df-stat"><div class="xfl-df-num">' +
          opts.riskPct + '%</div><div class="xfl-df-label">Risk %</div></div>');
      }

      // If there's nothing real to show, don't render an empty shell.
      if (stats.length === 0 && !opts.keyReasons && !opts.suggestedAction && !(opts.takeProfits && opts.takeProfits.length)) {
        el.innerHTML = '';
        return;
      }

      var html = '<div class="xfl-df">';
      html += '<div class="xfl-df-head">📋 Decision Report™</div>';
      if (stats.length) html += '<div class="xfl-df-grid">' + stats.join('') + '</div>';
      if (opts.takeProfits && opts.takeProfits.length) {
        html += '<div class="xfl-df-section"><strong>Take Profit Targets</strong><ul>' +
          opts.takeProfits.map(function (tp, i) { return '<li>TP' + (i + 1) + ': ' + tp + '</li>'; }).join('') +
          '</ul></div>';
      }
      if (opts.keyReasons && opts.keyReasons.length) {
        html += '<div class="xfl-df-section"><strong>Key Reasons</strong><ul>' +
          opts.keyReasons.map(function (r) { return '<li>' + r + '</li>'; }).join('') +
          '</ul></div>';
      }
      if (opts.suggestedAction) {
        html += '<div class="xfl-df-section"><strong>Suggested Action</strong><p>' +
          opts.suggestedAction + '</p></div>';
      }
      html += '</div>';
      el.innerHTML = html;
    } catch (e) { /* never let this break the underlying real analysis result */ }
  }

  window.renderDecisionFooter = render;
})();
