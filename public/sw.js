const CACHE_VERSION = 'v53';
const STATIC_CACHE = `drivstoff-static-${CACHE_VERSION}`;
const DATA_CACHE = `drivstoff-data-${CACHE_VERSION}`;

const STATIC_ASSETS = [
  '/',
  '/index.html',
  '/css/tokens.css',
  '/css/app.css',
  '/js/main.js',
  '/js/api.js',
  '/js/map.js',
  '/js/list.js',
  '/js/location.js',
  '/js/search.js',
  '/js/settings.js',
  '/js/station-sheet.js',
  '/js/kjede.js',
  '/js/stats.js',
  '/icon.svg',
  '/apple-touch-icon.png',
  '/favicon.ico',
  '/img/kjeder/circlek.png',
  '/img/kjeder/uno-x.png',
  '/img/kjeder/yx.png',
  '/img/kjeder/esso.png',
  '/img/kjeder/shell.png',
  '/img/kjeder/preem.png',
  '/img/kjeder/st1.png',
  '/img/kjeder/best.png',
  '/img/kjeder/oljeleverandoren.png',
  '/img/kjeder/tanken.png',
  '/img/kjeder/bunker-oil.svg',
  'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css',
  'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js',
];

// ── Install: precache statiske ressurser ──────────
self.addEventListener('install', (e) => {
  e.waitUntil(
    caches.open(STATIC_CACHE)
      .then(cache => cache.addAll(STATIC_ASSETS))
      .then(() => self.skipWaiting())
  );
});

// ── Activate: rydd opp gamle cacher ──────────────
self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(
        keys
          .filter(k => k !== STATIC_CACHE && k !== DATA_CACHE)
          .map(k => caches.delete(k))
      )
    ).then(() => self.clients.claim())
  );
});

// ── Fetch: strategi basert på request-type ────────
self.addEventListener('fetch', (e) => {
  const url = new URL(e.request.url);

  // POST-requests (pris, login osv.) — aldri cache
  if (e.request.method !== 'GET') return;

  // API-kall: network first, fall tilbake til cache
  if (url.pathname.startsWith('/api/')) {
    e.respondWith(networkFirstThenCache(e.request));
    return;
  }

  // Server-rendrede sider (oversikt, admin, prislogg): network first
  if (e.request.mode === 'navigate' && !STATIC_ASSETS.includes(url.pathname)) {
    e.respondWith(networkFirstThenCache(e.request));
    return;
  }

  // Karttiles (OpenStreetMap): cache first med nettverksfallback
  if (url.hostname.includes('tile.openstreetmap.org')) {
    e.respondWith(cacheFirstThenNetwork(e.request, DATA_CACHE));
    return;
  }

  // Statiske ressurser: stale-while-revalidate (rask fra cache, oppdateres i bakgrunnen)
  e.respondWith(staleWhileRevalidate(e.request, STATIC_CACHE));
});

// ── Cache-strategier ──────────────────────────────

async function networkFirstThenCache(request) {
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(DATA_CACHE);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    const cached = await caches.match(request);
    return cached || new Response(JSON.stringify({ error: 'Offline' }), {
      status: 503,
      headers: { 'Content-Type': 'application/json' },
    });
  }
}

async function staleWhileRevalidate(request, cacheName) {
  const cache = await caches.open(cacheName);
  const cached = await caches.match(request);

  // Hent fersk versjon i bakgrunnen uansett
  const fetchPromise = fetch(request).then(response => {
    if (response.ok) {
      cache.put(request, response.clone());
    }
    return response;
  }).catch(() => null);

  // Returner cache umiddelbart hvis tilgjengelig, ellers vent på nettverket
  return cached || await fetchPromise || new Response('Offline', { status: 503 });
}

async function cacheFirstThenNetwork(request, cacheName) {
  const cached = await caches.match(request);
  if (cached) return cached;

  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(cacheName);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    // Offline fallback for navigasjon
    if (request.mode === 'navigate') {
      return caches.match('/index.html');
    }
    return new Response('Offline', { status: 503 });
  }
}
