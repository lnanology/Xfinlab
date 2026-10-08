// XFINLAB service worker -- Web Push only (no offline caching / PWA
// scope creep here, that's a separate project). Registered with scope
// '/' from free-signals.html so push notifications work even when no
// XFINLAB tab is open.
self.addEventListener('push', function (event) {
  var data = {};
  try { data = event.data ? event.data.json() : {}; } catch (e) {}

  var title = data.title || 'XFINLAB';
  var body = data.body || '';
  var url = data.url || '/free-signals.html';

  event.waitUntil(
    self.registration.showNotification(title, {
      body: body,
      data: { url: url }
    })
  );
});

self.addEventListener('notificationclick', function (event) {
  event.notification.close();
  var url = (event.notification.data && event.notification.data.url) || '/free-signals.html';
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function (list) {
      for (var i = 0; i < list.length; i++) {
        var client = list[i];
        if (client.url.indexOf(url) !== -1 && 'focus' in client) return client.focus();
      }
      if (clients.openWindow) return clients.openWindow(url);
    })
  );
});
