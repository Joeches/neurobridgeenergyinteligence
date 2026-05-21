const CACHE_VERSION = "v3";
const STATIC_CACHE = `neurobridge-static-${CACHE_VERSION}`;
const RUNTIME_CACHE = `neurobridge-runtime-${CACHE_VERSION}`;

const STATIC_ASSETS = [
  "/",
  "/frontend/index.html",
  "/frontend/config.js",
  "/frontend/app.js",
  "/frontend/css/ui.css",
  "/frontend/pwa/manifest.json",
  "/frontend/assets/icons/icon-144.png"
];

/* =========================
   INSTALL
========================= */

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE).then(async (cache) => {
      for (const asset of STATIC_ASSETS) {
        try {
          await cache.add(asset);
        } catch (err) {
          console.warn("[SW] Failed to cache:", asset, err);
        }
      }
    })
  );

  self.skipWaiting();
});

/* =========================
   ACTIVATE
========================= */

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys.map((key) => {
          if (
            key !== STATIC_CACHE &&
            key !== RUNTIME_CACHE
          ) {
            return caches.delete(key);
          }
        })
      )
    )
  );

  self.clients.claim();
});

/* =========================
   FETCH
========================= */

self.addEventListener("fetch", (event) => {
  const req = event.request;
  const url = new URL(req.url);

  /* =========================
     NEVER CACHE API REQUESTS
  ========================= */

  if (url.pathname.startsWith("/api/")) {
    event.respondWith(networkOnly(req));
    return;
  }

  /* =========================
     STATIC ASSETS
  ========================= */

  if (
    req.destination === "style" ||
    req.destination === "script" ||
    req.destination === "image" ||
    req.destination === "font"
  ) {
    event.respondWith(staleWhileRevalidate(req));
    return;
  }

  /* =========================
     HTML NAVIGATION
  ========================= */

  if (req.mode === "navigate") {
    event.respondWith(networkFirst(req));
    return;
  }

  /* =========================
     DEFAULT
  ========================= */

  event.respondWith(
    caches.match(req).then((cached) => cached || fetch(req))
  );
});

/* =========================
   STRATEGIES
========================= */

async function networkOnly(request) {
  return fetch(request);
}

async function networkFirst(request) {
  try {
    const fresh = await fetch(request);

    const cache = await caches.open(RUNTIME_CACHE);
    cache.put(request, fresh.clone());

    return fresh;
  } catch (err) {
    const cached = await caches.match(request);

    if (cached) {
      return cached;
    }

    return caches.match("/frontend/index.html");
  }
}

async function staleWhileRevalidate(request) {
  const cache = await caches.open(RUNTIME_CACHE);

  const cached = await cache.match(request);

  const fetchPromise = fetch(request)
    .then((networkResponse) => {
      if (
        networkResponse &&
        networkResponse.status === 200
      ) {
        cache.put(request, networkResponse.clone());
      }

      return networkResponse;
    })
    .catch(() => cached);

  return cached || fetchPromise;
}

/* =========================
   MESSAGE EVENTS
========================= */

self.addEventListener("message", (event) => {
  if (event.data && event.data.type === "SKIP_WAITING") {
    self.skipWaiting();
  }
});

/* =========================
   ERROR HANDLING
========================= */

self.addEventListener("error", (event) => {
  console.error("[SW] Error:", event.message);
});

self.addEventListener("unhandledrejection", (event) => {
  console.error("[SW] Unhandled rejection:", event.reason);
});