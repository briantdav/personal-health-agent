// Minimal service worker: exists for PWA installability and faster static
// asset loads, not offline health data. Dashboard/trends/journal pages and
// their API calls are always network-first — showing stale recovery/sleep
// numbers from a cache would be actively misleading, not a nice-to-have
// offline fallback.

const CACHE_NAME = "health-portal-static-v1";
const STATIC_ASSETS = [
  "/static/style.css",
  "/static/trends.js",
  "/static/manifest.json",
  "/static/icons/icon-192.png",
  "/static/icons/icon-512.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))))
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (STATIC_ASSETS.includes(url.pathname)) {
    event.respondWith(caches.match(event.request).then((cached) => cached || fetch(event.request)));
    return;
  }
  event.respondWith(fetch(event.request).catch(() => caches.match(event.request)));
});
