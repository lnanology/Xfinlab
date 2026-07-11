/*
 * Shared "AI Loading Experience" overlay.
 *
 * Brand principle #4 from the Decision Intelligence repositioning spec:
 * 每個分析流程都要有「AI 正在工作」的即時回饋 (every analysis flow needs
 * real-time "AI is working" feedback). index.html already has a purely
 * decorative version of this on the homepage (cycleLiveSteps()); this file
 * is the REAL version — it's driven by actual in-flight API calls
 * (postApi/getApi in js/mvp-api.js, and chart-analysis.html's direct
 * fetch), not a fixed timer loop.
 *
 * Self-contained: injects its own overlay markup + styles into <body> on
 * first use, so pages only need to add a single <script> tag — no HTML/CSS
 * changes required per page. Reference-counted so overlapping calls (e.g. a
 * page that fires two requests back-to-back) don't flicker the overlay
 * closed early.
 *
 * Usage: window.startAiLoading() before a fetch, window.stopAiLoading()
 * in a finally block once the response (or error) is in hand. Both are
 * no-ops if called before the DOM is ready or if the overlay fails to
 * build for any reason -- this must never block or break an actual
 * analysis call.
 */
(function () {
  var STEPS = [
    { icon: '📊', label: 'Reading Market...' },
    { icon: '📰', label: 'Reading News...' },
    { icon: '📈', label: 'Scanning Charts...' },
    { icon: '🧠', label: 'Building Research...' },
    { icon: '🎯', label: 'Calculating Decision Score...' },
    { icon: '📄', label: 'Generating Final Report...' }
  ];
  var STEP_INTERVAL_MS = 1100;

  var _count = 0;
  var _timer = null;
  var _stepIndex = 0;
  var _built = false;
  var _overlay = null;
  var _hideTimeout = null;

  function _build() {
    if (_built) return;
    _built = true;

    var style = document.createElement('style');
    style.textContent =
      '#xfl-ai-loading-overlay{position:fixed;inset:0;z-index:9999;display:flex;' +
      'align-items:center;justify-content:center;background:rgba(17,17,17,0.45);' +
      'backdrop-filter:blur(3px);opacity:0;transition:opacity .2s ease;pointer-events:none}' +
      '#xfl-ai-loading-overlay.show{opacity:1;pointer-events:auto}' +
      '#xfl-ai-loading-card{background:var(--bg-card,#fff);border-radius:16px;' +
      'padding:1.75rem 2rem;width:min(360px,88vw);box-shadow:0 20px 60px rgba(0,0,0,0.25);' +
      'font-family:"Inter",sans-serif}' +
      '#xfl-ai-loading-card .xfl-head{font-size:0.8rem;font-weight:600;letter-spacing:.02em;' +
      'color:var(--accent-blue,#2563EB);margin-bottom:1rem;display:flex;align-items:center;gap:.4rem}' +
      '#xfl-ai-loading-card .xfl-head .xfl-dot{width:7px;height:7px;border-radius:50%;' +
      'background:var(--accent-blue,#2563EB);animation:xfl-pulse 1.1s ease-in-out infinite}' +
      '.xfl-step{display:flex;align-items:center;gap:.6rem;padding:.4rem 0;font-size:0.88rem;' +
      'color:var(--text-muted,#666);transition:color .2s ease,opacity .2s ease;opacity:0.45}' +
      '.xfl-step.active{color:var(--text-primary,#111);opacity:1;font-weight:500}' +
      '.xfl-step.done{color:var(--text-secondary,#333);opacity:0.75}' +
      '.xfl-step .xfl-icon{width:1.3em;text-align:center}' +
      '.xfl-step .xfl-check{margin-left:auto;color:var(--accent-green,#16A34A);' +
      'font-size:0.8rem;opacity:0}' +
      '.xfl-step.done .xfl-check{opacity:1}' +
      '@keyframes xfl-pulse{0%,100%{opacity:1}50%{opacity:.3}}';
    document.head.appendChild(style);

    var overlay = document.createElement('div');
    overlay.id = 'xfl-ai-loading-overlay';
    var stepsHtml = STEPS.map(function (s, i) {
      return '<div class="xfl-step" data-i="' + i + '">' +
        '<span class="xfl-icon">' + s.icon + '</span>' +
        '<span class="xfl-label">' + s.label + '</span>' +
        '<span class="xfl-check">✓</span>' +
        '</div>';
    }).join('');
    overlay.innerHTML =
      '<div id="xfl-ai-loading-card">' +
      '<div class="xfl-head"><span class="xfl-dot"></span>AI 正在分析緊真實市場數據</div>' +
      stepsHtml +
      '</div>';
    document.body.appendChild(overlay);
    _overlay = overlay;
  }

  function _render() {
    if (!_overlay) return;
    var els = _overlay.querySelectorAll('.xfl-step');
    els.forEach(function (el) {
      var i = parseInt(el.getAttribute('data-i'), 10);
      el.classList.toggle('active', i === _stepIndex);
      el.classList.toggle('done', i < _stepIndex);
    });
  }

  function _advance() {
    if (_stepIndex < STEPS.length - 1) {
      _stepIndex++;
      _render();
    }
    // Holds on the last step ("Generating Final Report...") if the real
    // call is still in flight -- never loops back to the start, since
    // that would look like the AI forgot what it was doing.
  }

  function start() {
    try {
      if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', start, { once: true });
        return;
      }
      _build();
      _count++;
      if (_hideTimeout) { clearTimeout(_hideTimeout); _hideTimeout = null; }
      if (_count === 1) {
        _stepIndex = 0;
        _render();
        _overlay.classList.add('show');
        _timer = setInterval(_advance, STEP_INTERVAL_MS);
      }
    } catch (e) { /* never let the loading UI break a real analysis call */ }
  }

  function stop() {
    try {
      _count = Math.max(0, _count - 1);
      if (_count === 0 && _overlay) {
        _overlay.classList.remove('show');
        if (_timer) { clearInterval(_timer); _timer = null; }
        // Small delay so the fade-out transition can finish before the
        // step state resets for the next call.
        _hideTimeout = setTimeout(function () { _stepIndex = 0; }, 250);
      }
    } catch (e) { /* no-op */ }
  }

  window.startAiLoading = start;
  window.stopAiLoading = stop;
})();
