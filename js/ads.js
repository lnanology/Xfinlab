/* 2026-08-09 (monetization P0, XFINLAB_Final_Strategy.md route 1): site-wide
   AdSense loader.

   Same "dormant until real config exists" convention as
   services/broker_affiliate_config.py and api/webhooks_paddle.py: PUBLISHER_ID
   below is deliberately empty. AJ has NOT applied for/been approved into a
   Google AdSense account yet -- that step requires his own identity and
   cannot be done on his behalf. Shipping a fake or placeholder publisher ID
   would either do nothing useful or (worse) get flagged by Google as invalid
   traffic setup before the account even exists.

   How to actually turn this on:
     1. Apply at https://adsense.google.com with a real Google account (AJ
        does this himself -- account creation/identity verification is not
        something this codebase or an agent can do for him).
     2. Once approved, paste the publisher ID (format "ca-pub-XXXXXXXXXXXXXXXX")
        into PUBLISHER_ID below.
     3. This script then auto-injects the AdSense loader script and fills any
        <div class="ad-slot"> container on the page. Until then, every
        ad-slot div is simply left empty -- no broken iframes, no fake ads,
        nothing that looks like it's working when it isn't.

   Ad slots are deliberately placed away from analysis results/AI output
   (never inside a result card) to avoid any appearance of a paid placement
   influencing XFINLAB's research -- same posture as the broker affiliate CTA
   docstring ("never let commission change the analysis"). */
(function () {
  var PUBLISHER_ID = ""; // e.g. "ca-pub-1234567890123456" -- fill in once AdSense approves the account

  if (!PUBLISHER_ID) return; // silently no-op, see docstring above

  var loader = document.createElement("script");
  loader.async = true;
  loader.src = "https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=" + PUBLISHER_ID;
  loader.crossOrigin = "anonymous";
  document.head.appendChild(loader);

  document.querySelectorAll(".ad-slot").forEach(function (slot) {
    var ins = document.createElement("ins");
    ins.className = "adsbygoogle";
    ins.style.display = "block";
    ins.setAttribute("data-ad-client", PUBLISHER_ID);
    ins.setAttribute("data-ad-slot", slot.dataset.slot || "");
    ins.setAttribute("data-ad-format", "auto");
    ins.setAttribute("data-full-width-responsive", "true");
    slot.appendChild(ins);
    try {
      (window.adsbygoogle = window.adsbygoogle || []).push({});
    } catch (e) {
      /* AdSense not ready yet on this slot -- non-fatal, next slot continues */
    }
  });
})();
