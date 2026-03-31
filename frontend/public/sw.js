// loom offline service worker
// caches app shell and api responses for offline viewing

const CACHE_NAME = 'loom-v1';
const API_CACHE = 'loom-api-v1';

// app shell resources to precache
const SHELL_URLS = [
  '/',
  '/index.html',
];

// api paths to cache for offline viewing
const CACHEABLE_API = [
  '/api/v1/cases',
  '/api/v1/health',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(SHELL_URLS);
    }),
  );
  // activate immediately
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  // clean old caches
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys
          .filter(
            (k) => k !== CACHE_NAME && k !== API_CACHE,
          )
          .map((k) => caches.delete(k)),
      );
    }),
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // only handle get requests
  if (event.request.method !== 'GET') return;

  // api requests: network-first, fallback to cache
  if (url.pathname.startsWith('/api/v1/')) {
    // cache case list, individual cases, and case-scoped
    // read-only resources for offline access
    const shouldCache = CACHEABLE_API.some(
      (p) => url.pathname === p,
    ) || url.pathname.match(
      /^\/api\/v1\/cases\/[^/]+(\/assets|\/timeline|\/annotations)?$/,
    );

    if (shouldCache) {
      event.respondWith(
        fetch(event.request)
          .then((response) => {
            const clone = response.clone();
            caches.open(API_CACHE).then((cache) => {
              cache.put(event.request, clone);
            });
            return response;
          })
          .catch(() => {
            return caches.match(event.request);
          }),
      );
      return;
    }
    // non-cacheable api: just pass through
    return;
  }

  // app shell: network-first for navigation, cache-first
  // for static assets
  if (
    event.request.mode === 'navigate'
    || url.pathname === '/'
  ) {
    event.respondWith(
      fetch(event.request).catch(() => {
        return caches.match('/index.html');
      }),
    );
    return;
  }

  // static assets (js, css): cache-first
  if (
    url.pathname.endsWith('.js')
    || url.pathname.endsWith('.css')
    || url.pathname.endsWith('.woff2')
    || url.pathname.endsWith('.svg')
  ) {
    event.respondWith(
      caches.match(event.request).then((cached) => {
        if (cached) return cached;
        return fetch(event.request).then((response) => {
          const clone = response.clone();
          caches.open(CACHE_NAME).then((cache) => {
            cache.put(event.request, clone);
          });
          return response;
        });
      }),
    );
  }
});
