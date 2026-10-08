/*
 * 2026-08-09 -- homepage scroll-reveal ("每區的進入及離開會淡出淡入").
 *
 * Behaviour, confirmed with AJ before building: each [data-reveal] /
 * [data-reveal-stagger] element fades in + moves up 20px the FIRST time
 * it enters the viewport while scrolling down. It does NOT fade back out
 * when scrolled past -- a "reveal once, stay visible" pattern (same as
 * Stripe/Linear-style marketing sites), not a "flash every time you
 * scroll past it" pattern, which would be disorienting and hurt reading.
 *
 * [data-reveal-stagger] containers (card grids: Top Opportunity, Market
 * Opportunity Board, pricing cards) get the class toggle on the
 * CONTAINER; css/style.css's [data-reveal-stagger].is-revealed > *
 * nth-child delay rules stagger the children's fade-in automatically --
 * this file never touches the children directly, so it keeps working
 * even after index.html's own JS re-renders a grid's innerHTML with real
 * data (e.g. renderTopOpp()/renderNineCat()) after this observer has
 * already fired on the container.
 *
 * Deliberately vanilla IntersectionObserver, no library -- this is a
 * homepage-only visual polish layer, not worth a new dependency.
 */
(function () {
  var prefersReducedMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  function reveal() {
    var targets = document.querySelectorAll('[data-reveal], [data-reveal-stagger]');
    if (!targets.length) return;

    if (prefersReducedMotion || typeof IntersectionObserver === 'undefined') {
      // No motion, or old browser without IO -- just show everything now.
      targets.forEach(function (el) { el.classList.add('is-revealed'); });
      return;
    }

    var observer = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            entry.target.classList.add('is-revealed');
            observer.unobserve(entry.target); // once only -- never re-hide on scroll-out
          }
        });
      },
      { threshold: 0.12, rootMargin: '0px 0px -40px 0px' }
    );

    targets.forEach(function (el) { observer.observe(el); });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', reveal);
  } else {
    reveal();
  }
})();
