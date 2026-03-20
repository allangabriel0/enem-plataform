// Service Worker — ENEM Studies
// Só faz cache de assets estáticos (CSS, JS, fontes). Vídeos NUNCA são cacheados aqui.
const CACHE_NAME = 'enem-static-v1';
const STATIC_ASSETS = [
  '/static/css/style.css',
  '/static/js/app.js',
];

self.addEventListener('install', (e) => {
  e.waitUntil(
    caches.open(CACHE_NAME).then(c => c.addAll(STATIC_ASSETS)).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (e) => {
  const url = new URL(e.request.url);
  // Nunca intercepta stream de vídeo, API, ou navegação
  if (url.pathname.startsWith('/stream/') ||
      url.pathname.startsWith('/api/') ||
      e.request.mode === 'navigate') {
    return;
  }
  // Para assets estáticos: cache-first
  if (url.pathname.startsWith('/static/')) {
    e.respondWith(
      caches.match(e.request).then(cached => cached || fetch(e.request).then(resp => {
        const clone = resp.clone();
        caches.open(CACHE_NAME).then(c => c.put(e.request, clone));
        return resp;
      }))
    );
  }
});
