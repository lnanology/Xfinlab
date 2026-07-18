// XFINLAB proactive Web Push subscribe prompt.
// A dismissible bottom-center toast, shown a couple seconds after page
// load, distinct from free-signals.html's passive 🔔 button:
//   - Guest (no xfinlab_token): hooks with "Get free Top Opportunity
//     alerts" -- Top Opportunity is the flashy homepage feature, used
//     here as the attention-grabbing reason to opt in before the visitor
//     has any account relationship with XFINLAB yet.
//   - Logged in (has xfinlab_token): reminds with "Subscribe to daily
//     alerts" (same wording/key as free-signals.html's button) --
//     framed as "you're already a user, don't miss the daily signals."
// Both paths subscribe to the exact same push subscription under the
// hood (js/push-subscribe.js's window.XFLPush) -- there's only one
// notification type today (the daily Free Signals push), this is just
// two different marketing hooks into the same opt-in.
//
// Requires js/push-subscribe.js to be included first on the page.
(function () {
  var DISMISS_KEY = 'xfl_push_prompt_dismissed_at';
  var DISMISS_COOLDOWN_MS = 14 * 24 * 60 * 60 * 1000; // 14 days

  function t(key, fallback) {
    return (typeof I18N !== 'undefined' && I18N.translations && I18N.translations[key]) || fallback;
  }

  function isLoggedIn() {
    return !!localStorage.getItem('xfinlab_token');
  }

  function recentlyDismissed() {
    var raw = localStorage.getItem(DISMISS_KEY);
    if (!raw) return false;
    var ts = parseInt(raw, 10);
    return !isNaN(ts) && (Date.now() - ts) < DISMISS_COOLDOWN_MS;
  }

  function markDismissed() {
    localStorage.setItem(DISMISS_KEY, String(Date.now()));
  }

  function shouldShow() {
    if (!window.XFLPush || !window.XFLPush.isSupported()) return false;
    if (window.XFLPush.isSubscribed()) return false;
    if (recentlyDismissed()) return false;
    if (document.getElementById('xflPushPrompt')) return false;
    return true;
  }

  function buildToast() {
    var loggedIn = isLoggedIn();
    var title = loggedIn
      ? t('push_loggedin_title', 'Want the daily signals delivered to you?')
      : ('🎯 ' + t('push_guest_title', 'Get free Top Opportunity alerts'));
    var btnLabel = loggedIn
      ? t('freesig_push_subscribe', 'Subscribe to daily alerts')
      : t('push_guest_btn', 'Enable Notifications');
    var dismissLabel = t('push_dismiss', 'No thanks');

    var wrap = document.createElement('div');
    wrap.id = 'xflPushPrompt';
    wrap.style.cssText = 'position:fixed;left:50%;bottom:24px;transform:translateX(-50%);z-index:10000;' +
      'background:var(--bg-card,#FFFFFF);border:1px solid var(--border-color,#000000);border-radius:12px;' +
      'padding:14px 16px;box-shadow:0 8px 32px rgba(0,0,0,0.2);display:flex;align-items:center;gap:14px;' +
      'max-width:min(92vw,420px);font-family:inherit;';

    var textEl = document.createElement('div');
    textEl.style.cssText = 'color:var(--text-primary,#000000);font-size:0.85rem;font-weight:600;flex:1;line-height:1.4;';
    textEl.textContent = title;

    var actions = document.createElement('div');
    actions.style.cssText = 'display:flex;flex-direction:column;gap:6px;flex-shrink:0;';

    var subBtn = document.createElement('button');
    subBtn.type = 'button';
    subBtn.textContent = btnLabel;
    subBtn.style.cssText = 'background:var(--accent-orange,#f59e0b);color:#0d1525;border:none;padding:8px 14px;' +
      'border-radius:8px;font-weight:700;font-size:0.8rem;cursor:pointer;white-space:nowrap;font-family:inherit;';

    var dismissBtn = document.createElement('button');
    dismissBtn.type = 'button';
    dismissBtn.textContent = dismissLabel;
    dismissBtn.style.cssText = 'background:none;border:none;color:var(--text-muted,#666666);font-size:0.72rem;' +
      'cursor:pointer;padding:2px;font-family:inherit;';

    subBtn.onclick = async function () {
      subBtn.disabled = true;
      try {
        await window.XFLPush.subscribe();
      } catch (e) {
        console.error(e);
      }
      removeToast();
    };
    dismissBtn.onclick = function () {
      markDismissed();
      removeToast();
    };

    actions.appendChild(subBtn);
    actions.appendChild(dismissBtn);
    wrap.appendChild(textEl);
    wrap.appendChild(actions);
    return wrap;
  }

  function removeToast() {
    var el = document.getElementById('xflPushPrompt');
    if (el && el.parentNode) el.parentNode.removeChild(el);
  }

  function maybeShow() {
    if (!shouldShow()) return;
    document.body.appendChild(buildToast());
  }

  function init() {
    // Small delay so it doesn't compete with the page's initial load /
    // other onboarding UI for attention.
    setTimeout(maybeShow, 2500);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
