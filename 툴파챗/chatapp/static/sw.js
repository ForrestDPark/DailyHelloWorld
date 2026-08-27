// ★ "채팅방에 새 메시지 있으면 사용자들한테도 알람이 가게 해달라" 요청
// (2026-08-27) — 웹 푸시 수신 전용 서비스 워커. 캐싱/오프라인은 다루지
// 않는다 — 순수 푸시 알림만.
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
