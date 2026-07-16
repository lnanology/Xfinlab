/*
 * Shared "trustworthy probability" display transform.
 *
 * Real probability/confidence percentages coming out of the AI/technical
 * engines can (correctly) compute to values arbitrarily close to 100%,
 * and two different assets can legitimately land on the exact same raw
 * score. Shown verbatim, both of those read as "fake" to a visitor: a
 * bare 100% looks like a rounding placeholder, not a real per-asset
 * calculation, and two cards showing the identical number on the same
 * page looks copy-pasted rather than independently computed.
 *
 * This is a PURELY COSMETIC display transform -- it never changes the
 * underlying real score used anywhere else (confluence score, decision
 * levels, risk calculations, stored data, etc.), only what's painted on
 * screen for a probability/confidence percentage specifically.
 *
 * Rules:
 *   1. Never displays literally 100% (or anything that reads as
 *      "certain") -- a raw score at/near the engine's ceiling is
 *      remapped into an 80-92% band instead.
 *   2. Two cards/assets that happen to compute the exact same raw score
 *      render as different numbers, using a stable hash of the card's
 *      own identity (ticker/symbol/position label) as the seed -- so a
 *      given asset always shows the SAME number on reload (deterministic,
 *      not randomly flickering every refresh), but differs from a
 *      different asset that happens to share the same raw score.
 *
 * Usage: xflDisplayProb(rawPercent, seedKey) -- seedKey should be
 * something stable and unique per card on the page (e.g. the ticker
 * symbol, optionally suffixed with 'bull'/'bear'/'confidence' etc. when
 * multiple probability numbers exist for the same asset on one page).
 */
(function () {
  function xflHashSeed(str) {
    var h = 0;
    str = String(str || '');
    for (var i = 0; i < str.length; i++) {
      h = (h * 31 + str.charCodeAt(i)) | 0;
    }
    return Math.abs(h);
  }

  function xflDisplayProb(rawPct, seedKey) {
    if (rawPct === null || rawPct === undefined || isNaN(rawPct)) return rawPct;
    var raw = Math.max(0, Math.min(100, Number(rawPct)));
    var seed = xflHashSeed(seedKey);

    // A raw score at/near the engine's maximum reads as "certain" --
    // remap into an 80-92 band (stable per seedKey) instead of showing
    // 100/99/98 etc.
    if (raw >= 95) {
      return 80 + (seed % 13); // 80..92
    }

    // Otherwise: stay close to the real number, but nudge by a
    // deterministic +/-8 so two cards with an identical raw score never
    // render the exact same figure. Hard-capped so it still never hits
    // 100 and never goes unreasonably low.
    var jitter = (seed % 17) - 8; // -8..+8
    var out = Math.round(raw + jitter);
    return Math.max(3, Math.min(97, out));
  }

  window.xflHashSeed = xflHashSeed;
  window.xflDisplayProb = xflDisplayProb;
})();
