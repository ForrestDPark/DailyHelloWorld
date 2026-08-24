let currentRoom = null;
let lastId = 0;
let pollTimer = null;

const roomListView = document.getElementById("room-list-view");
const chatView = document.getElementById("chat-view");
const roomListEl = document.getElementById("room-list");
const messagesEl = document.getElementById("messages");

function parseRoomFromHash() {
  const m = location.hash.match(/^#room=(.+)$/);
  return m ? decodeURIComponent(m[1]) : null;
}

// ★ "이거 좀 정신건강에 무서우니까 캐릭터이름 뒤에 (가상) 붙여달라"는 요청
// (2026-08-24) — 실제 인물이 아니라 AI 페르소나라는 걸 화면에서 항상 표시.
// 서버/워커가 쓰는 실제 이름("동찬이형")은 그대로 두고, 화면 표시에만 붙인다.
function displayName(name) {
  if (name === "user" || name === "전체 채팅방") return name;
  return `${name} (가상)`;
}

async function showRoomList() {
  currentRoom = null;
  if (pollTimer) clearTimeout(pollTimer);
  chatView.classList.add("hidden");
  roomListView.classList.remove("hidden");
  try {
    const res = await fetch("/api/rooms");
    const rooms = await res.json();
    roomListEl.innerHTML = "";
    if (!rooms.length) {
      roomListEl.innerHTML = '<div class="empty-hint">아직 페르소나가 없습니다</div>';
      return;
    }
    for (const r of rooms) {
      const item = document.createElement("a");
      item.href = "#room=" + encodeURIComponent(r.room_id);
      item.className = "room-item";
      const avatarChar = r.room_id === "group" ? "☺" : r.label[0];
      const roomLabel = r.room_id === "group" ? r.label : displayName(r.label);
      item.innerHTML = `
        <div class="avatar">${avatarChar}</div>
        <div class="room-info">
          <div class="room-name">${escapeHtml(roomLabel)}</div>
          <div class="room-preview">${r.last_message ? escapeHtml(r.last_message) : "대화를 시작해보세요"}</div>
        </div>
      `;
      roomListEl.appendChild(item);
    }
  } catch (e) {
    roomListEl.innerHTML = '<div class="empty-hint">방 목록을 불러오지 못했습니다</div>';
    console.error(e);
  }
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

function showChatView(roomId) {
  currentRoom = roomId;
  lastId = 0;
  messagesEl.innerHTML = "";
  roomListView.classList.add("hidden");
  chatView.classList.remove("hidden");
  document.getElementById("room-title").textContent = roomId === "group" ? "전체 채팅방" : displayName(roomId);
  poll();
}

function appendMessage(m) {
  const el = document.createElement("div");
  el.className = "msg " + (m.sender === "user" ? "msg-user" : "msg-persona");
  const sender = document.createElement("div");
  sender.className = "sender";
  sender.textContent = m.sender === "user" ? "나" : displayName(m.sender);
  const body = document.createElement("div");
  body.className = "body";
  body.textContent = m.content;
  el.appendChild(sender);
  el.appendChild(body);
  messagesEl.appendChild(el);
  el.scrollIntoView({ behavior: "smooth", block: "end" });
}

async function poll() {
  if (!currentRoom) return;
  try {
    const res = await fetch(`/api/messages?room_id=${encodeURIComponent(currentRoom)}&since_id=${lastId}`);
    const messages = await res.json();
    for (const m of messages) {
      appendMessage(m);
      lastId = m.id;
    }
  } catch (e) {
    console.error(e);
  }
  pollTimer = setTimeout(poll, 2000);
}

document.getElementById("composer").addEventListener("submit", async (e) => {
  e.preventDefault();
  if (!currentRoom) return;
  const input = document.getElementById("input");
  const content = input.value.trim();
  if (!content) return;
  input.value = "";
  try {
    await fetch("/api/messages", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content, room_id: currentRoom }),
    });
  } catch (e) {
    console.error(e);
  }
});

document.getElementById("back-btn").addEventListener("click", () => {
  location.hash = "";
});

function route() {
  const room = parseRoomFromHash();
  if (room) {
    showChatView(room);
  } else {
    showRoomList();
  }
}

window.addEventListener("hashchange", route);
route();
