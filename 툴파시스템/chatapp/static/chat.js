let currentRoom = null;
let lastId = 0;
let pollTimer = null;
let canWrite = true; // /api/whoami로 초기화 — 공유 링크로 들어온 읽기 전용 방문자는 false

// ★ "링크 공유해서 읽기만 되게 해달라" 요청(2026-08-25) — 쓰기 불가 방문자는
// 아예 입력창/사진첨부/답장 UI를 숨긴다(서버도 403으로 막지만, UI에서부터
// 안 보이게 해서 혼란을 줄임).
async function initWriteAccess() {
  try {
    const res = await fetch("/api/whoami");
    const data = await res.json();
    canWrite = !!data.can_write;
  } catch (e) {
    canWrite = true; // 조회 실패 시 기존 동작(서버가 어차피 막아줌) 유지
  }
  if (!canWrite) document.body.classList.add("read-only");
}

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

// ★ "안 읽은 메시지 있으면 안읽음 표시해달라" 요청(2026-08-25) — 서버는
// 상태를 안 들고 있으므로(단일 사용자 개인 앱), "이 방에서 마지막으로 읽은
// 메시지 id"를 브라우저 localStorage에 기기별로 저장한다.
function lastReadKey(roomId) {
  return `tulpa_last_read_${roomId}`;
}
function getLastRead(roomId) {
  return parseInt(localStorage.getItem(lastReadKey(roomId)) || "0", 10);
}
function markRoomRead(roomId, messageId) {
  if (!messageId) return;
  const current = getLastRead(roomId);
  if (messageId > current) localStorage.setItem(lastReadKey(roomId), String(messageId));
}

function renderRoomItem(r) {
  const item = document.createElement("a");
  item.href = "#room=" + encodeURIComponent(r.room_id);
  item.className = "room-item";
  const isMeta = r.room_id === "group" || r.is_group_room;
  const avatarChar = r.room_id === "group" ? "☺" : r.label[0];
  const roomLabel = isMeta ? r.label : displayName(r.label);
  const unread = r.last_message_id && r.last_message_id > getLastRead(r.room_id);
  item.innerHTML = `
    <div class="avatar">${avatarChar}</div>
    <div class="room-info">
      <div class="room-name">${escapeHtml(roomLabel)}${unread ? '<span class="unread-dot"></span>' : ""}</div>
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
  setReplyTarget(null);
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
  // ★ "그룹채팅방 초대 기능" + "누가 방에 있는지 보고 싶다" 요청(2026-08-25) —
  // 진짜 그룹 회의방(Notion "그룹" 필드에서 나온 방, is_group_room)에서만
  // 참여자 보기 버튼을 보여준다. 전체 채팅방(room_id="group")은 원래 전원
  // 참여라 해당 없음. 참여자 "보기"는 읽기 전용 방문자도 가능 — 초대만
  // canWrite로 따로 막는다(toggleInvitePanel 안에서).
  const inviteBtn = document.getElementById("invite-btn");
  const isGroupMeetingRoom = cached && cached.is_group_room && roomId !== "group";
  inviteBtn.classList.toggle("hidden", !isGroupMeetingRoom);
  document.getElementById("invite-panel").classList.add("hidden");
  if (cached && cached.last_message_id) markRoomRead(roomId, cached.last_message_id);
  poll();
}

async function toggleInvitePanel() {
  const panel = document.getElementById("invite-panel");
  const memberList = document.getElementById("member-list");
  const inviteSection = document.getElementById("invite-section");
  const inviteList = document.getElementById("invite-list");
  if (!panel.classList.contains("hidden")) {
    panel.classList.add("hidden");
    return;
  }
  memberList.innerHTML = '<div class="empty-hint">불러오는 중...</div>';
  panel.classList.remove("hidden");
  try {
    const res = await fetch(`/api/rooms/${encodeURIComponent(currentRoom)}/members`);
    const { members, available } = await res.json();
    memberList.innerHTML = "";
    if (!members.length) {
      memberList.innerHTML = '<div class="empty-hint">아직 참여자가 없습니다</div>';
    }
    for (const name of members) {
      const chip = document.createElement("span");
      chip.className = "member-chip";
      chip.textContent = displayName(name);
      memberList.appendChild(chip);
    }
    // ★ 초대 후보 목록은 쓰기 권한이 있을 때만 — 읽기 전용 방문자는 참여자
    // 목록만 보고, 초대 버튼은 보이지 않는다.
    inviteSection.classList.toggle("hidden", !canWrite);
    if (canWrite) {
      inviteList.innerHTML = "";
      if (!available.length) {
        inviteList.innerHTML = '<div class="empty-hint">초대할 수 있는 사람이 없습니다</div>';
      } else {
        for (const name of available) {
          const btn = document.createElement("button");
          btn.type = "button";
          btn.className = "invite-candidate";
          btn.textContent = displayName(name);
          btn.addEventListener("click", () => inviteToRoom(name));
          inviteList.appendChild(btn);
        }
      }
    }
  } catch (e) {
    memberList.innerHTML = '<div class="empty-hint">불러오지 못했습니다</div>';
    console.error(e);
  }
}

async function inviteToRoom(personaName) {
  try {
    await fetch(`/api/rooms/${encodeURIComponent(currentRoom)}/invite`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ persona_name: personaName }),
    });
  } catch (e) {
    console.error(e);
  }
  document.getElementById("invite-panel").classList.add("hidden");
}

document.getElementById("invite-btn").addEventListener("click", toggleInvitePanel);

// ★ "채팅 친 시각이 메시지 옆에 작게 나오면 좋겠다" 요청(2026-08-25).
// created_at은 서버가 UTC ISO8601로 내려주므로 new Date()가 알아서 로컬
// 시간대로 바꿔준다.
function formatTime(isoString) {
  const d = new Date(isoString);
  if (isNaN(d)) return "";
  return d.toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" });
}

const IMAGE_MARKER_RE = /!\[\]\((\/uploads\/[^)]+)\)/;

// ★ "한명한테 답장하는 기능" 요청(2026-08-25) — 그룹/회의방에서 페르소나
// 메시지의 이름을 탭하면 그 사람에게만 답장하는 모드로 들어간다. @멘션을
// 직접 타이핑할 필요 없이 서버에 reply_to로 실어 보낸다.
let replyTarget = null;
const replyBanner = document.getElementById("reply-banner");
const replyBannerText = document.getElementById("reply-banner-text");

function setReplyTarget(name) {
  replyTarget = name;
  if (name) {
    replyBannerText.textContent = `${displayName(name)}에게 답장`;
    replyBanner.classList.remove("hidden");
  } else {
    replyBanner.classList.add("hidden");
  }
}

document.getElementById("reply-cancel-btn").addEventListener("click", () => setReplyTarget(null));

function appendMessage(m) {
  const el = document.createElement("div");
  el.className = "msg " + (m.sender === "user" ? "msg-user" : "msg-persona");
  const sender = document.createElement("div");
  sender.className = "sender";
  sender.textContent = m.sender === "user" ? "나" : displayName(m.sender);
  const cached = roomsCache.get(currentRoom);
  const isMetaRoom = currentRoom === "group" || (cached && cached.is_group_room);
  if (m.sender !== "user" && isMetaRoom && canWrite) {
    // 그룹/회의방에서만 "답장" 대상 지정이 의미가 있다(1:1 방은 이미 그 한
    // 명뿐이라 필요 없음).
    sender.classList.add("sender-clickable");
    sender.title = "탭해서 이 사람에게만 답장";
    sender.addEventListener("click", () => setReplyTarget(m.sender));
  }
  const body = document.createElement("div");
  body.className = "body";
  const imageMatch = IMAGE_MARKER_RE.exec(m.content);
  if (imageMatch) {
    const img = document.createElement("img");
    img.src = imageMatch[1];
    img.className = "chat-image";
    body.appendChild(img);
    const rest = m.content.replace(IMAGE_MARKER_RE, "").trim();
    if (rest) {
      const caption = document.createElement("div");
      caption.textContent = rest;
      body.appendChild(caption);
    }
  } else {
    body.textContent = m.content;
  }
  const time = document.createElement("div");
  time.className = "msg-time";
  time.textContent = formatTime(m.created_at);
  el.appendChild(sender);
  el.appendChild(body);
  el.appendChild(time);
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
    if (messages.length) markRoomRead(currentRoom, lastId);
  } catch (e) {
    console.error(e);
  }
  pollTimer = setTimeout(poll, 2000);
}

async function sendMessage(content) {
  if (!currentRoom || !content) return;
  try {
    await fetch("/api/messages", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content, room_id: currentRoom, reply_to: replyTarget }),
    });
  } catch (e) {
    console.error(e);
  }
  setReplyTarget(null);
}

document.getElementById("composer").addEventListener("submit", async (e) => {
  e.preventDefault();
  const input = document.getElementById("input");
  const content = input.value.trim();
  if (!content) return;
  input.value = "";
  await sendMessage(content);
});

// ★ "채팅창에 이미지 업로드해서 서로 분석하면 좋겠다" 요청(2026-08-25) —
// 사진을 /api/upload로 올리고, 받은 URL을 ![](url) 마크다운으로 채팅
// 메시지에 실어 보낸다. 워커(persona_worker.py)가 같은 마커를 찾아 로컬
// 파일로 읽어 AI에게 실제로 보여준다.
const imageInput = document.getElementById("image-input");
document.getElementById("upload-btn").addEventListener("click", () => imageInput.click());
imageInput.addEventListener("change", async () => {
  const file = imageInput.files[0];
  imageInput.value = "";
  if (!file || !currentRoom) return;
  const formData = new FormData();
  formData.append("file", file);
  try {
    const res = await fetch("/api/upload", { method: "POST", body: formData });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      alert(err.detail || "이미지 업로드 실패");
      return;
    }
    const { url } = await res.json();
    await sendMessage(`![](${url})`);
  } catch (e) {
    console.error(e);
    alert("이미지 업로드 실패");
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
initWriteAccess().then(route);
