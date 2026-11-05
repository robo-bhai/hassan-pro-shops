// Minimal service worker (PWA ke liye).
// Sirf Tesseract (OCR) ki bari files cache hoti hain: cache-first, taake OCR dobara foran khule aur internet ke baghair chale.
// Baqi sab requests seedha network par jati hain, isliye purana data kabhi stale nahi hoga.
var TESS_CACHE = 'tesseract-v1';

self.addEventListener('install', function (event) {
  self.skipWaiting();
});

self.addEventListener('activate', function (event) {
  event.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(keys.filter(function (k) {
        return k.indexOf('tesseract-') === 0 && k !== TESS_CACHE;
      }).map(function (k) { return caches.delete(k); }));
    }).then(function () { return self.clients.claim(); })
  );
});

self.addEventListener('fetch', function (event) {
  var req = event.request;
  if (req.method !== 'GET') return;
  var url = new URL(req.url);
  if (url.origin !== self.location.origin || url.pathname.indexOf('/tesseract/') === -1) return;   // not an OCR file -> network as usual
  event.respondWith(
    caches.open(TESS_CACHE).then(function (cache) {
      return cache.match(req).then(function (hit) {
        if (hit) return hit;
        return fetch(req).then(function (res) {
          if (res && res.ok) cache.put(req, res.clone());
          return res;
        });
      });
    })
  );
});
