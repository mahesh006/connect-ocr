const cacheName = "flask-PWA-v3";
const filesToCache = [
  "/",
  "/login",
  "/static/app.js",
  "/static/script.js",
  "/static/style.css",
  "/static/images/pwa-light.png",
];

self.addEventListener("install", function (e) {
  console.log("[ServiceWorker] Install");
  e.waitUntil(
    caches.open(cacheName).then(function (cache) {
      console.log("[ServiceWorker] Caching app shell");
      return cache.addAll(filesToCache);
    })
  );
});

self.addEventListener("activate", function (e) {
  console.log("[ServiceWorker] Activate");
  e.waitUntil(
    caches.keys().then(function (keyList) {
      return Promise.all(
        keyList.map(function (key) {
          if (key !== cacheName) {
            console.log("[ServiceWorker] Removing old cache", key);
            return caches.delete(key);
          }
        })
      );
    })
  );
  return self.clients.claim();
});

self.addEventListener("fetch", function (e) {
  console.log("[ServiceWorker] Fetch", e.request.url);
  e.respondWith(
    caches.match(e.request).then(function (response) {
      return (
        response ||
        fetch(e.request).catch((error) => {
          console.log("Fetch failed; returning offline page instead.", error);
          let url = e.request.url;
          let extension = url.split(".").pop();

          if (extension === "jpg" || extension === "png") {
            const FALLBACK_IMAGE = ``;

            return Promise.resolve(
              new Response(FALLBACK_IMAGE, {
                headers: {
                  "Content-Type": "image/svg+xml",
                },
              })
            );
          }

          return caches.match("offline.html");
        })
      );
    })
  );
});
