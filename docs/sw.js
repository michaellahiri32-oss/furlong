/* Furlong service worker — installable + offline, always fresh.
   HTML shell and data: network-first with cache:'reload' so we bypass the HTTP
   cache and always get the newest code + data; fall back to cache when offline.
   Static icons: cache-first. */
const SHELL = 'furlong-shell-v4';
const DATA = 'furlong-data-v4';
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
  const isJSON = url.pathname.endsWith('.json') && !url.pathname.endsWith('manifest.webmanifest');
  const isShell = e.request.mode === 'navigate'
    || url.pathname.endsWith('/') || url.pathname.endsWith('index.html');

  if (isJSON || isShell) {
    // network-first, bypassing the HTTP cache so updates always win
    e.respondWith(
      fetch(e.request, { cache: 'reload' }).then(res => {
        const copy = res.clone();
        caches.open(isJSON ? DATA : SHELL).then(c => c.put(e.request, copy));
        return res;
      }).catch(() => caches.match(e.request).then(r => r || caches.match('./index.html')))
    );
    return;
  }
  e.respondWith(caches.match(e.request).then(r => r || fetch(e.request)));
});
