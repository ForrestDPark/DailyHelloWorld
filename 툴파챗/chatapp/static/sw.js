const CACHE_NAME = "tulpachat-shell-20260912-v1";
const OFFLINE_URL = "/static/offline.html";

// 서버 재시작 중에도 설치된 웹앱이 흰 화면만 보이지 않도록 정비 안내 화면은
// 로컬에 보관한다. 실제 앱과 API는 항상 네트워크 우선이라 오래된 대화가
// 캐시에서 잘못 표시되지 않는다.
self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.add(OFFLINE_URL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  if (event.request.mode !== "navigate") return;
  event.respondWith(fetch(event.request).catch(() => caches.match(OFFLINE_URL)));
});

// ★ "채팅방에 새 메시지 있으면 사용자들한테도 알람이 가게 해달라" 요청
// (2026-08-27) — 웹 푸시 수신.
self.addEventListener("push", (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch (e) {
    data = { title: "툴파챗", body: event.data ? event.data.text() : "" };
  }
  const title = data.title || "툴파챗";
  event.waitUntil(
    self.registration.showNotification(title, {
      body: data.body || "",
      tag: data.url || "tulpachat",
      data: { url: data.url || "/" },
    })
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = (event.notification.data && event.notification.data.url) || "/";
  event.waitUntil(
    clients.matchAll({ type: "window", includeUncontrolled: true }).then((clientList) => {
      for (const client of clientList) {
        if ("focus" in client) {
          client.navigate(url);
          return client.focus();
        }
      }
      if (clients.openWindow) return clients.openWindow(url);
    })
  );
});
