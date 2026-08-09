/* 2026-08-09 (monetization P0, XFINLAB_Final_Strategy.md route 1): "support
   XFINLAB" footer link, pointing at a Ko-fi/Buy Me a Coffee page.

   Same "dormant until real config exists" convention as js/ads.js and
   services/broker_affiliate_config.py: SUPPORT_URL below is deliberately
   empty. AJ has not created a Ko-fi/Buy Me a Coffee account yet -- that is
   his own account-creation step, not something this codebase can do for
   him. Until it's filled in, this script does nothing: no dead link, no
   placeholder that looks like a real donation button but goes nowhere.

   How to actually turn this on:
     1. Create a free creator page at https://ko-fi.com or
        https://buymeacoffee.com (AJ does this himself).
     2. Paste the page URL into SUPPORT_URL below.
     3. This script then appends one small link into the page's <footer>,
        next to the existing Terms/Privacy/Risk Warning links -- same visual
        weight as those, not a flashy floating widget, so it doesn't re-open
        the mobile floating-widget-stacking problem this codebase already
        fixed (tasks #135/#300/#609). Intentionally NOT added to
        js/mobile-widget-dock.js's DOCK_IDS -- that dock is reserved for the
        6 existing core widgets; a 7th competing for mobile screen space
        there would crowd it. */
(function () {
  var SUPPORT_URL = ""; // e.g. "https://ko-fi.com/xfinlab" -- fill in once the account exists

  if (!SUPPORT_URL) return; // silently no-op, see docstring above

  function addLink() {
    var footer = document.querySelector("footer");
    if (!footer || footer.querySelector(".xfl-support-link")) return;
    var a = document.createElement("a");
    a.href = SUPPORT_URL;
    a.className = "xfl-support-link";
    a.target = "_blank";
    a.rel = "noopener";
    a.textContent = "Support XFINLAB";
    a.style.marginLeft = "8px";
    footer.appendChild(a);
  }

  if ("loading" === document.readyState) {
    document.addEventListener("DOMContentLoaded", addLink);
  } else {
    addLink();
  }
})();
