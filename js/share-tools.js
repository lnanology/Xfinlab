/*
 * Shared "Share System" bar -- Share → Image → PDF → Link, per the brand
 * spec's Share System requirement (每個分析：Share → Image → PDF → Link
 * 方便分享).
 *
 * Design constraints (kept consistent with this whole session's "never
 * fabricate" rule):
 *   - Image/PDF are real client-side captures of the actual real result
 *     DOM (html2canvas + jsPDF, lazy-loaded from cdnjs only when a user
 *     actually clicks Image/PDF -- no extra weight on normal page loads).
 *   - Link is only rendered when the calling page passes a real, working
 *     shareUrl -- i.e. a URL that, when opened, re-runs the SAME real
 *     analysis via URL query params (see each page's own "prefill from
 *     URL" logic). This is a live re-run, not a frozen/stale snapshot
 *     presented as if it were dynamic. Pages where the input can't be
 *     reconstructed from a URL (an uploaded chart image, a free-form chat)
 *     simply don't pass a shareUrl, so the Link button is omitted rather
 *     than shown as a broken/fake feature.
 *
 * Usage: window.renderShareBar(containerIdOrEl, resultElId, { shareUrl, filename })
 */
(function () {
  var _styled = false;
  var _libsPromise = null;

  function _ensureStyle() {
    if (_styled) return;
    _styled = true;
    var style = document.createElement('style');
    style.textContent =
      '.xfl-share-bar{display:flex;gap:8px;flex-wrap:wrap;margin:1rem 0;align-items:center}' +
      '.xfl-share-btn{display:inline-flex;align-items:center;gap:6px;padding:8px 14px;' +
      'border-radius:8px;border:1px solid var(--border-color,#E5E7EB);background:var(--bg-card,#fff);' +
      'color:var(--text-primary,#111);font-size:0.82rem;font-family:"Inter",sans-serif;cursor:pointer;' +
      'transition:border-color .15s ease,background .15s ease}' +
      '.xfl-share-btn:hover{border-color:var(--accent-blue,#2563EB);background:var(--bg-secondary,#F8FAFC)}' +
      '.xfl-share-btn:disabled{opacity:0.55;cursor:wait}' +
      '.xfl-share-toast{font-size:0.78rem;color:var(--accent-green,#16A34A);opacity:0;' +
      'transition:opacity .2s ease}' +
      '.xfl-share-toast.show{opacity:1}';
    document.head.appendChild(style);
  }

  function _loadScript(src) {
    return new Promise(function (resolve, reject) {
      var s = document.createElement('script');
      s.src = src;
      s.onload = resolve;
      s.onerror = function () { reject(new Error('load failed: ' + src)); };
      document.head.appendChild(s);
    });
  }

  function _ensureLibs() {
    if (_libsPromise) return _libsPromise;
    _libsPromise = Promise.all([
      window.html2canvas ? Promise.resolve() :
        _loadScript('https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js'),
      (window.jspdf && window.jspdf.jsPDF) ? Promise.resolve() :
        _loadScript('https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js')
    ]);
    return _libsPromise;
  }

  function _showToast(toastEl, msg) {
    toastEl.textContent = msg;
    toastEl.classList.add('show');
    setTimeout(function () { toastEl.classList.remove('show'); }, 2200);
  }

  function render(container, resultElId, opts) {
    try {
      var el = typeof container === 'string' ? document.getElementById(container) : container;
      if (!el) return;
      opts = opts || {};
      var filename = opts.filename || 'xfinlab-analysis';
      _ensureStyle();

      var html =
        '<div class="xfl-share-bar">' +
        '<button type="button" class="xfl-share-btn" data-act="image">📷 Image</button>' +
        '<button type="button" class="xfl-share-btn" data-act="pdf">📄 PDF</button>' +
        (opts.shareUrl ? '<button type="button" class="xfl-share-btn" data-act="link">🔗 Link</button>' : '') +
        '<span class="xfl-share-toast"></span>' +
        '</div>';
      el.innerHTML = html;

      var toast = el.querySelector('.xfl-share-toast');
      var btnImage = el.querySelector('[data-act="image"]');
      var btnPdf = el.querySelector('[data-act="pdf"]');
      var btnLink = el.querySelector('[data-act="link"]');

      function withResultEl(fn) {
        var resultEl = document.getElementById(resultElId);
        if (!resultEl) { _showToast(toast, '⚠️ 搵唔到結果內容'); return; }
        fn(resultEl);
      }

      if (btnImage) {
        btnImage.addEventListener('click', function () {
          btnImage.disabled = true;
          btnImage.textContent = '處理緊...';
          withResultEl(function (resultEl) {
            _ensureLibs().then(function () {
              return window.html2canvas(resultEl, { backgroundColor: '#ffffff', scale: 2 });
            }).then(function (canvas) {
              var a = document.createElement('a');
              a.href = canvas.toDataURL('image/png');
              a.download = filename + '.png';
              a.click();
            }).catch(function () {
              _showToast(toast, '⚠️ 匯出圖片失敗，請重試');
            }).finally(function () {
              btnImage.disabled = false;
              btnImage.textContent = '📷 Image';
            });
          });
        });
      }

      if (btnPdf) {
        btnPdf.addEventListener('click', function () {
          btnPdf.disabled = true;
          btnPdf.textContent = '處理緊...';
          withResultEl(function (resultEl) {
            _ensureLibs().then(function () {
              return window.html2canvas(resultEl, { backgroundColor: '#ffffff', scale: 2 });
            }).then(function (canvas) {
              var jsPDF = window.jspdf.jsPDF;
              var imgData = canvas.toDataURL('image/png');
              var pxToMm = 0.264583;
              var wMm = canvas.width * pxToMm;
              var hMm = canvas.height * pxToMm;
              var orientation = wMm > hMm ? 'l' : 'p';
              var pdf = new jsPDF({ orientation: orientation, unit: 'mm', format: [wMm, hMm] });
              pdf.addImage(imgData, 'PNG', 0, 0, wMm, hMm);
              pdf.save(filename + '.pdf');
            }).catch(function () {
              _showToast(toast, '⚠️ 匯出PDF失敗，請重試');
            }).finally(function () {
              btnPdf.disabled = false;
              btnPdf.textContent = '📄 PDF';
            });
          });
        });
      }

      if (btnLink) {
        btnLink.addEventListener('click', function () {
          var url = opts.shareUrl;
          function done() { _showToast(toast, '✅ 已複製連結（打開會即時重新運行同一個分析）'); }
          if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(url).then(done).catch(function () {
              window.prompt('複製呢個連結：', url);
            });
          } else {
            window.prompt('複製呢個連結：', url);
          }
        });
      }
    } catch (e) { /* never let the share bar break the underlying real result */ }
  }

  window.renderShareBar = render;
})();
