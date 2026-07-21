// Slide-puzzle CAPTCHA widget -- self-hosted, no third-party script.
// See services/captcha_service.py for the backend design. Exposes
// window.XFLCaptcha = { mount(containerId), getVerifyToken(), reset() }.
(function () {
  var API = (typeof window.API !== 'undefined' && window.API) || 'https://api.xfinlab.com/api';

  function t(key, fallback) {
    return (typeof I18N !== 'undefined' && I18N.translations && I18N.translations[key]) || fallback;
  }

  var state = {
    challengeToken: null,
    pieceSize: 42,
    imgWidth: 320,
    imgHeight: 160,
    verifyToken: null,
    dragging: false,
    dragStartTime: null,
    els: null,
  };

  function buildDom(container) {
    container.innerHTML =
      '<div class="xfl-captcha" style="max-width:320px">' +
      '  <div class="xfl-captcha-stage" style="position:relative;border-radius:8px;overflow:hidden;background:#222;">' +
      '    <img class="xfl-captcha-bg" style="display:block;width:100%;height:auto;user-select:none;pointer-events:none;" draggable="false">' +
      '    <img class="xfl-captcha-piece" style="position:absolute;top:0;left:0;user-select:none;">' +
      '    <div class="xfl-captcha-status" style="position:absolute;top:6px;left:8px;font-size:0.72rem;color:#fff;background:rgba(0,0,0,0.5);padding:2px 8px;border-radius:10px;"></div>' +
      '  </div>' +
      '  <div class="xfl-captcha-track" style="position:relative;margin-top:8px;height:36px;background:var(--bg,#f1f5f9);border:1px solid var(--border-color,#cbd5e1);border-radius:8px;">' +
      '    <div class="xfl-captcha-track-label" style="position:absolute;inset:0;display:flex;align-items:center;justify-content:center;font-size:0.78rem;color:var(--text-muted,#64748b);pointer-events:none;"></div>' +
      '    <div class="xfl-captcha-handle" style="position:absolute;top:-1px;left:-1px;width:38px;height:38px;background:var(--accent-blue,#2563EB);color:#fff;border-radius:8px;display:flex;align-items:center;justify-content:center;cursor:grab;font-size:1rem;box-shadow:0 2px 6px rgba(0,0,0,0.25);">&#8594;</div>' +
      '  </div>' +
      '</div>';

    return {
      root: container,
      bg: container.querySelector('.xfl-captcha-bg'),
      piece: container.querySelector('.xfl-captcha-piece'),
      status: container.querySelector('.xfl-captcha-status'),
      track: container.querySelector('.xfl-captcha-track'),
      trackLabel: container.querySelector('.xfl-captcha-track-label'),
      handle: container.querySelector('.xfl-captcha-handle'),
    };
  }

  function setStatus(text, ok) {
    if (!state.els) return;
    state.els.status.textContent = text;
    state.els.status.style.background = ok === true ? 'rgba(16,185,129,0.85)' : (ok === false ? 'rgba(239,68,68,0.85)' : 'rgba(0,0,0,0.5)');
  }

  async function loadChallenge() {
    setStatus(t('captcha_loading', 'Loading...'), null);
    state.verifyToken = null;
    if (state.els) {
      state.els.handle.style.left = '-1px';
      state.els.piece.style.left = '0px';
      state.els.trackLabel.textContent = t('captcha_drag_hint', 'Drag the slider to fit the puzzle piece →');
    }
    try {
      var res = await fetch(API + '/captcha/challenge');
      var data = await res.json();
      state.challengeToken = data.challenge_token;
      state.pieceSize = data.piece_size;
      state.imgWidth = data.img_width;
      state.imgHeight = data.img_height;
      if (state.els) {
        state.els.bg.src = data.background_image;
        state.els.piece.src = data.piece_image;
        state.els.piece.style.top = (data.piece_y / data.img_height * 100) + '%';
        state.els.piece.style.width = (data.piece_size / data.img_width * 100) + '%';
      }
      setStatus('', null);
    } catch (e) {
      setStatus(t('captcha_load_error', 'Failed to load, tap to retry'), false);
    }
  }

  function trackWidth() {
    return state.els.track.clientWidth - 38;
  }

  function bgPixelWidth() {
    return state.els.bg.clientWidth || state.imgWidth;
  }

  function onDragMove(clientX, startClientX, startLeft) {
    var delta = clientX - startClientX;
    var maxLeft = trackWidth();
    var newLeft = Math.max(0, Math.min(maxLeft, startLeft + delta));
    state.els.handle.style.left = newLeft + 'px';
    // Map handle position (0..maxLeft) to piece x position (0..bgWidth-pieceSize)
    var ratio = maxLeft > 0 ? newLeft / maxLeft : 0;
    var maxPieceX = bgPixelWidth() - (state.pieceSize / state.imgWidth * bgPixelWidth());
    var pieceX = ratio * maxPieceX;
    state.els.piece.style.left = pieceX + 'px';
    return pieceX;
  }

  async function submitVerify(pieceXDisplayed) {
    // Convert displayed (scaled) pixel position back to the original
    // image's coordinate space (background image is rendered at
    // whatever width the CSS lays it out at, but the challenge's
    // target_x is in the original IMG_WIDTH coordinate space).
    var scale = state.imgWidth / bgPixelWidth();
    var realX = pieceXDisplayed * scale;
    var elapsed = state.dragStartTime ? (Date.now() - state.dragStartTime) : null;
    setStatus(t('captcha_verifying', 'Verifying...'), null);
    try {
      var res = await fetch(API + '/captcha/verify', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ challenge_token: state.challengeToken, x: realX, elapsed_ms: elapsed }),
      });
      var data = await res.json();
      if (data.valid) {
        state.verifyToken = data.verify_token;
        setStatus(t('captcha_success', '✓ Verified'), true);
        state.els.handle.style.cursor = 'default';
      } else {
        setStatus(t('captcha_failed', '✗ Not quite, try again'), false);
        setTimeout(loadChallenge, 900);
      }
    } catch (e) {
      setStatus(t('captcha_load_error', 'Failed to load, tap to retry'), false);
    }
  }

  function wireDrag(els) {
    var startX = 0;
    var startLeft = 0;

    function pointerDown(clientX) {
      if (state.verifyToken) return; // already solved, no need to redrag
      state.dragging = true;
      state.dragStartTime = Date.now();
      startX = clientX;
      startLeft = parseFloat(els.handle.style.left || '-1') || 0;
      els.handle.style.cursor = 'grabbing';
    }
    function pointerMove(clientX) {
      if (!state.dragging) return;
      onDragMove(clientX, startX, startLeft);
    }
    function pointerUp(clientX) {
      if (!state.dragging) return;
      state.dragging = false;
      els.handle.style.cursor = 'grab';
      var finalX = onDragMove(clientX, startX, startLeft);
      var pieceLeftPx = parseFloat(els.piece.style.left || '0');
      submitVerify(pieceLeftPx);
    }

    els.handle.addEventListener('mousedown', function (e) { e.preventDefault(); pointerDown(e.clientX); });
    document.addEventListener('mousemove', function (e) { pointerMove(e.clientX); });
    document.addEventListener('mouseup', function (e) { pointerUp(e.clientX); });

    els.handle.addEventListener('touchstart', function (e) { pointerDown(e.touches[0].clientX); }, { passive: true });
    document.addEventListener('touchmove', function (e) { if (state.dragging) pointerMove(e.touches[0].clientX); }, { passive: true });
    document.addEventListener('touchend', function (e) { pointerUp(e.changedTouches[0].clientX); });

    els.status.addEventListener('click', function () {
      if (!state.verifyToken) loadChallenge();
    });
  }

  window.XFLCaptcha = {
    mount: function (containerId) {
      var container = document.getElementById(containerId);
      if (!container) return;
      state.els = buildDom(container);
      wireDrag(state.els);
      loadChallenge();
    },
    getVerifyToken: function () {
      return state.verifyToken;
    },
    reset: function () {
      loadChallenge();
    },
  };
})();
