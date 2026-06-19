const CACHE = 'mg-v6';
const STATIC = [
  '/static/style.css',
  '/static/player.js',
  '/static/script.js',
  '/static/download-manager.js',
  '/static/library.js',
  '/static/manifest.json',
  '/static/icon-192.png',
  '/static/icon-512.png',
  '/static/icon-192.svg',
  '/static/icon-512.svg',
];

self.addEventListener('install', (e) => {
  e.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(STATIC))
  );
  self.skipWaiting();
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', (e) => {
  const url = new URL(e.request.url);
  if (url.origin !== self.location.origin) return;
  if (STATIC.includes(url.pathname)) {
    e.respondWith(
      caches.open(CACHE).then((cache) =>
        cache.match(e.request, { ignoreSearch: true }).then((hit) => hit || fetch(e.request).then((r) => { cache.put(e.request, r.clone()); return r; }))
      )
    );
    return;
  }
  e.respondWith(
    fetch(e.request).catch(() => caches.match(e.request))
  );
});