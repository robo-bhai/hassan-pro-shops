// Minimal service worker (PWA ke liye). Koi caching nahi, isliye purana data kabhi stale nahi hoga.
self.addEventListener('install', function (event) {
  self.skipWaiting();
});

self.addEventListener('activate', function (event) {
  event.waitUntil(self.clients.claim());
});

self.addEventListener('fetch', function (event) {
  // Sab requests seedha network par jati hain
  return;
});
