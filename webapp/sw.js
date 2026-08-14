/* Furlong service worker — installable + offline.
   Shell: cache-first (fast, works offline). Data: network-first (fresh),
   falling back to the last cached copy when there's no connection. */
const SHELL = 'furlong-shell-v2';
const DATA = 'furlong-data-v2';
const SHELL_FILES = [
  './', './index.html', './manifest.webmanifest',
  './icon-192.png', './icon-512.png', './icon-maskable-512.png',
  './apple-touch-icon.png'
];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(SHELL).then(c => c.addAll(SHELL_FILES)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys => Promise.all(
      keys.filter(k => k !== SHELL && k !== DATA).map(k => caches.delete(k))
    )).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);
  if (url.pathname.endsWith('.json') && !url.pathname.endsWith('manifest.webmanifest')) {
    // network-first for the daily data files (data.json, data-tomorrow.json)
    e.respondWith(
      fetch(e.request).then(res => {
        const copy = res.clone();
        caches.open(DATA).then(c => c.put(e.request, copy));
        return res;
      }).catch(() => caches.match(e.request))
    );
    return;
  }
  // cache-first for the app shell
  e.respondWith(caches.match(e.request).then(r => r || fetch(e.request)));
});
