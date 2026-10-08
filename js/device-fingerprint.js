/*
 * Self-hosted device fingerprint (2026-07-24 anti-abuse batch, layer 5 of
 * the registration architecture requested in chat: "Device Fingerprint").
 * Free -- no FingerprintJS/third-party service, just the browser's own
 * Canvas/WebGL/Web Crypto APIs. Combines a canvas rendering hash + WebGL
 * renderer string + screen/timezone/locale/hardware hints into one
 * SHA-256 hash via window.crypto.subtle (built into every modern
 * browser, no library needed).
 *
 * This is a best-effort "roughly the same device" signal for catching
 * bulk/bot registrations that keep switching email + IP but reuse the
 * same browser -- like every fingerprinting technique it can be evaded
 * by someone who deliberately tries to (incognito, hardened browsers,
 * canvas-noise extensions), so it's ONE input to services/risk_score_
 * service.py's weighted score, never a sole gate on its own. Failing to
 * produce a fingerprint at all (old browser, blocked API, script error)
 * degrades to sending no fingerprint field -- backend/auth/user_model.py
 * treats that as a neutral "no signal", never a hard registration
 * failure.
 */
(function () {
  function getCanvasFingerprint() {
    try {
      const canvas = document.createElement('canvas');
      canvas.width = 220;
      canvas.height = 40;
      const ctx = canvas.getContext('2d');
      if (!ctx) return 'canvas-unavailable';
      ctx.textBaseline = 'top';
      ctx.font = '14px Arial';
      ctx.fillStyle = '#f60';
      ctx.fillRect(0, 0, 100, 20);
      ctx.fillStyle = '#069';
      ctx.fillText('XFINLAB fp 1234', 2, 2);
      ctx.fillStyle = 'rgba(102, 204, 0, 0.7)';
      ctx.fillText('XFINLAB fp 1234', 4, 8);
      return canvas.toDataURL();
    } catch (e) {
      return 'canvas-unavailable';
    }
  }

  function getWebglFingerprint() {
    try {
      const canvas = document.createElement('canvas');
      const gl = canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
      if (!gl) return 'webgl-unavailable';
      const dbgInfo = gl.getExtension('WEBGL_debug_renderer_info');
      const vendor = dbgInfo ? gl.getParameter(dbgInfo.UNMASKED_VENDOR_WEBGL) : gl.getParameter(gl.VENDOR);
      const renderer = dbgInfo ? gl.getParameter(dbgInfo.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER);
      return `${vendor}~${renderer}`;
    } catch (e) {
      return 'webgl-unavailable';
    }
  }

  async function sha256Hex(text) {
    if (window.crypto && window.crypto.subtle && window.crypto.subtle.digest) {
      try {
        const buf = await window.crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
        return Array.from(new Uint8Array(buf)).map(b => b.toString(16).padStart(2, '0')).join('');
      } catch (e) {
        // fall through to the non-crypto fallback below
      }
    }
    // Very old browsers without SubtleCrypto -- a cheap non-cryptographic
    // hash so the feature still degrades gracefully instead of the whole
    // fingerprint attempt throwing and blocking registration.
    let h = 0;
    for (let i = 0; i < text.length; i++) {
      h = (h * 31 + text.charCodeAt(i)) | 0;
    }
    return 'fallback-' + Math.abs(h).toString(16);
  }

  window.XFLFingerprint = {
    // Returns a Promise<string> -- always resolves (never rejects), worst
    // case with a low-entropy fallback hash rather than throwing, so
    // callers can safely `await` this without their own try/catch.
    async get() {
      try {
        const parts = [
          getCanvasFingerprint(),
          getWebglFingerprint(),
          screen.width + 'x' + screen.height + 'x' + screen.colorDepth,
          (Intl.DateTimeFormat().resolvedOptions().timeZone) || '',
          navigator.language || '',
          (navigator.languages || []).join(','),
          navigator.hardwareConcurrency || '',
          navigator.platform || '',
        ].join('|');
        return await sha256Hex(parts);
      } catch (e) {
        return '';
      }
    },
  };
})();
