// XFINLAB Web Push subscribe helper.
// Exposes window.XFLPush = { isSupported, isSubscribed, subscribe, unsubscribe }
// Used by free-signals.html's subscribe bell. Kept as a standalone
// module (not auto-injecting any UI itself) since right now there's
// only one call site -- if more pages want a subscribe button later,
// they can call these functions directly.
(function () {
  var API = 'https://api.xfinlab.com/api';
  var STORAGE_KEY = 'xfl_push_subscribed';

  function urlBase64ToUint8Array(base64String) {
    var padding = '='.repeat((4 - (base64String.length % 4)) % 4);
    var base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
    var rawData = atob(base64);
    var outputArray = new Uint8Array(rawData.length);
    for (var i = 0; i < rawData.length; ++i) outputArray[i] = rawData.charCodeAt(i);
    return outputArray;
  }

  function isSupported() {
    return 'serviceWorker' in navigator && 'PushManager' in window;
  }

  function isSubscribed() {
    return localStorage.getItem(STORAGE_KEY) === '1';
  }

  async function subscribe() {
    if (!isSupported()) throw new Error('unsupported');

    var permission = await Notification.requestPermission();
    if (permission !== 'granted') throw new Error('permission-denied');

    var reg = await navigator.serviceWorker.register('/sw.js');
    await navigator.serviceWorker.ready;

    var keyRes = await fetch(API + '/push/vapid-public-key');
    var keyData = await keyRes.json();

    var existing = await reg.pushManager.getSubscription();
    var sub = existing || await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(keyData.key)
    });

    var token = localStorage.getItem('xfinlab_token') || '';
    var url = API + '/push/subscribe' + (token ? ('?token=' + encodeURIComponent(token)) : '');
    await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(sub.toJSON())
    });

    localStorage.setItem(STORAGE_KEY, '1');
    return true;
  }

  async function unsubscribe() {
    if (!isSupported()) return;
    var reg = await navigator.serviceWorker.getRegistration('/sw.js');
    if (!reg) { localStorage.removeItem(STORAGE_KEY); return; }
    var sub = await reg.pushManager.getSubscription();
    if (sub) {
      await fetch(API + '/push/unsubscribe', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ endpoint: sub.endpoint })
      });
      await sub.unsubscribe();
    }
    localStorage.removeItem(STORAGE_KEY);
  }

  window.XFLPush = { isSupported: isSupported, isSubscribed: isSubscribed, subscribe: subscribe, unsubscribe: unsubscribe };
})();
