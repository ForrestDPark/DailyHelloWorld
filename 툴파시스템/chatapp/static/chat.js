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

function renderRoomItem(r) {
  const item = document.createElement("a");
  item.href = "#room=" + encodeURIComponent(r.room_id);
  item.className = "room-item";
  const isMeta = r.room_id === "group" || r.is_group_room;
  const avatarChar = r.room_id === "group" ? "☺" : r.label[0];
  const roomLabel = isMeta ? r.label : displayName(r.label);
  item.innerHTML = `
    <div class="avatar">${avatarChar}</div>
    <div class="room-info">
      <div class="room-name">${escapeHtml(roomLabel)}</div>
      <div class="room-preview">${r.last_message ? escapeHtml(r.last_message) : "대화를 시작해보세요"}</div>
    </div>
  `;
  return item;
}

// ★ "페르소나 목록도 그룹화하는 게 좋을거같아" 요청(2026-08-25) — Notion
// 프로필의 "그룹" 필드(서버가 group_name으로 내려줌)를 기준으로 방 목록을
// 묶어서 보여준다. 전체 채팅방(room_id="group")과 그룹 회의방
// (is_group_room=true, "동찬이형+양승윤 묶어서 회의방" 요청으로 추가)은
// 그룹 헤더 없이 맨 위에 단독으로 두고, 그룹이 없는 개별 페르소나는
// "그룹 없음"으로 모은다.
function groupRooms(rooms) {
  const solo = rooms.filter((r) => r.room_id === "group" || r.is_group_room);
  const rest = rooms.filter((r) => r.room_id !== "group" && !r.is_group_room);
  const groups = new Map();
  for (const r of rest) {
    const key = r.group_name || "그룹 없음";
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(r);
  }
  const orderedKeys = [...groups.keys()].sort((a, b) => {
    if (a === "그룹 없음") return 1;
    if (b === "그룹 없음") return -1;
    return a.localeCompare(b, "ko");
  });
  return { solo, groups, orderedKeys };
}

let roomsCache = new Map(); // room_id -> room object, showChatView()에서 제목/메타 표시용

async function showRoomList() {
  currentRoom = null;
  if (pollTimer) clearTimeout(pollTimer);
  chatView.classList.add("hidden");
  roomListView.classList.remove("hidden");
  try {
    const res = await fetch("/api/rooms");
    const rooms = await res.json();
    roomsCache = new Map(rooms.map((r) => [r.room_id, r]));
    roomListEl.innerHTML = "";
    if (!rooms.length) {
      roomListEl.innerHTML = '<div class="empty-hint">아직 페르소나가 없습니다</div>';
      return;
    }
    const { solo, groups, orderedKeys } = groupRooms(rooms);
    for (const r of solo) {
      roomListEl.appendChild(renderRoomItem(r));
    }
    for (const key of orderedKeys) {
      const header = document.createElement("div");
      header.className = "group-header";
      header.textContent = key;
      roomListEl.appendChild(header);
      for (const r of groups.get(key)) {
        roomListEl.appendChild(renderRoomItem(r));
      }
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
  // ★ 그룹 회의방(예: "예술가부흥프로젝트")은 페르소나 이름이 아니라 방
  // 제목이므로 (가상) 라벨을 안 붙인다 — roomsCache로 room_id가 그룹
  // 회의방인지 확인한다(캐시에 없으면 URL을 직접 편집해 들어온 경우일
  // 수 있으니 안전하게 페르소나 이름으로 간주).
  const cached = roomsCache.get(roomId);
  const isMeta = roomId === "group" || (cached && cached.is_group_room);
  const title = cached ? cached.label : roomId;
  document.getElementById("room-title").textContent = isMeta ? title : displayName(title);
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
