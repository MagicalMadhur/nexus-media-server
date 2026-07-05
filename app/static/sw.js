const CACHE_NAME = 'media-server-v1';
const ASSETS_TO_CACHE = [
  '/',
  '/static/css/main.css',
  '/static/js/app.js',
  '/static/manifest.json',
  '/static/icons/app-icon-192.png',
  '/static/icons/app-icon-512.png',
  'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(ASSETS_TO_CACHE);
    })
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames.map((name) => {
          if (name !== CACHE_NAME) {
            return caches.delete(name);
          }
        })
      );
    })
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  // Only intercept GET requests
  if (event.request.method !== 'GET') return;
  
  // Don't intercept API requests or streams
  if (event.request.url.includes('/api/') || event.request.url.includes('/player/')) {
      return;
  }

  event.respondWith(
    fetch(event.request).catch(() => {
      return caches.match(event.request).then((response) => {
        if (response) {
          return response;
        }
        // If offline and not in cache, fallback to offline page or just root
        if (event.request.mode === 'navigate') {
          return caches.match('/');
        }
      });
    })
  );
});
