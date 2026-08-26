let currentRoom = null;
let lastId = 0;
let pollTimer = null;
let canWrite = true; // /api/whoami로 초기화 — 공유 링크로 들어온 읽기 전용 방문자는 false
let myUsername = null; // 로그인 계정의 실제 아이디(2026-08-26 다중 계정) — 내 메시지 판별용
let amOwner = false; // 소유자 계정으로 로그인했는지 — 권한 관리(⚙️) 패널 노출 여부에 씀

const authView = document.getElementById("auth-view");
const roomListView = document.getElementById("room-list-view");
const chatView = document.getElementById("chat-view");
const roomListEl = document.getElementById("room-list");
const messagesEl = document.getElementById("messages");

// ★ 2026-08-26: 세션 쿠키가 만료됐거나(180일 지남) 로그인 자체가 안 된
// 상태에서 API를 호출하면 서버가 401을 준다. fetch를 감싸서 401을 만나면
// 바로 로그인 화면으로 돌려보낸다 — 사용 중간에 세션이 끊겨도 흰 화면/무한
// 로딩 대신 다시 로그인하면 되는 걸 바로 알 수 있게.
async function apiFetch(url, opts) {
  const res = await fetch(url, opts);
  if (res.status === 401) {
    if (pollTimer) clearTimeout(pollTimer);
    showAuthView("세션이 만료되었습니다. 다시 로그인해주세요.");
    throw new Error("unauthorized");
  }
  if (res.status === 403) {
    // ★ 2026-08-26: "1:1 방은 다른 참여자에게 안 보이게 해달라" 요청 — 방
    // 목록에서 이미 빠지지만, URL 해시를 직접 편집해서 들어오려는 시도까지
    // 막아야 해서 서버도 403을 준다. 여기서 방 목록으로 튕겨보낸다.
    if (pollTimer) clearTimeout(pollTimer);
    const data = await res.clone().json().catch(() => ({}));
    alert(data.detail || "접근할 수 없습니다");
    location.hash = "";
    throw new Error("forbidden");
  }
  return res;
}

// ★ "로그인/가입 기능을 만들면 좋겠다"는 요청(2026-08-26) — 다른 사용자도
// 계정만 있으면 채팅에 메시지를 남길 수 있게 열면서, 예전엔 브라우저
// 네이티브 Basic Auth 팝업이 하던 로그인을 화면 안 폼으로 옮겼다(가입
// 흐름은 팝업으로는 만들 수 없어서 필수적인 변경).
let authMode = "login";

function setAuthMode(mode) {
  authMode = mode;
  document.querySelectorAll(".auth-tab").forEach((el) => {
    el.classList.toggle("active", el.dataset.mode === mode);
  });
  document.getElementById("auth-submit").textContent = mode === "login" ? "로그인" : "가입하기";
  document.getElementById("auth-error").classList.add("hidden");
}

document.querySelectorAll(".auth-tab").forEach((el) => {
  el.addEventListener("click", () => setAuthMode(el.dataset.mode));
});

function showAuthView(message) {
  authView.classList.remove("hidden");
  roomListView.classList.add("hidden");
  chatView.classList.add("hidden");
  const errorEl = document.getElementById("auth-error");
  if (message) {
    errorEl.textContent = message;
    errorEl.classList.remove("hidden");
  } else {
    errorEl.classList.add("hidden");
  }
}

document.getElementById("auth-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const username = document.getElementById("auth-username").value.trim();
  const password = document.getElementById("auth-password").value;
  const errorEl = document.getElementById("auth-error");
  errorEl.classList.add("hidden");
  try {
    const res = await fetch(`/api/auth/${authMode === "login" ? "login" : "signup"}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    const data = await res.json();
    if (!res.ok) {
      errorEl.textContent = data.detail || "실패했습니다";
      errorEl.classList.remove("hidden");
      return;
    }
    myUsername = data.username;
    amOwner = !!data.is_owner;
    canWrite = true;
    authView.classList.add("hidden");
    initAccountChip();
    route();
  } catch (err) {
    errorEl.textContent = "네트워크 오류입니다";
    errorEl.classList.remove("hidden");
    console.error(err);
  }
});

function initAccountChip() {
  const chip = document.getElementById("account-chip");
  if (!myUsername) {
    chip.classList.add("hidden");
    document.getElementById("admin-btn").classList.add("hidden");
    document.getElementById("new-room-btn").classList.add("hidden");
    document.getElementById("persona-manager-btn").classList.add("hidden");
    document.getElementById("profiles-btn").classList.add("hidden");
    return;
  }
  document.getElementById("account-name").textContent = myUsername;
  chip.classList.remove("hidden");
  // ★ "모든 사람한테 유이 꾸밀 권한을 주지 말고 내 허락하에 그 사람에게
  // 권한을 줄 수 있게 해달라" 요청(2026-08-26) — 권한 관리 버튼은 소유자
  // 로그인일 때만 보인다.
  document.getElementById("admin-btn").classList.toggle("hidden", !amOwner);
  // ★ "사용자가 자기만의 페르소나를 만들고, 단체톡방도 만들 수 있게 해달라"
  // 요청(2026-08-26) — 로그인한 계정이면 누구나 쓸 수 있다(소유자 전용 아님).
  document.getElementById("new-room-btn").classList.remove("hidden");
  document.getElementById("persona-manager-btn").classList.remove("hidden");
  document.getElementById("profiles-btn").classList.remove("hidden");
}

document.getElementById("logout-btn").addEventListener("click", async () => {
  try {
    await fetch("/api/auth/logout", { method: "POST" });
  } catch (e) {
    console.error(e);
  }
  myUsername = null;
  amOwner = false;
  location.hash = "";
  showAuthView();
});

// ★ 2026-08-26: 소유자 전용 권한 관리 패널 — 계정별로 유이(UI 개발자
// 페르소나)에게 말 걸어 응답받을 권한을 부여/회수한다. 실제 실행(파일
// 반영) 승인은 항상 소유자만 할 수 있어서(worker의 owner-only 게이트)
// 이 권한은 어디까지나 "제안을 받아볼 수 있는지"만 결정한다.
async function renderAdminUsers() {
  const list = document.getElementById("admin-user-list");
  list.innerHTML = '<div class="empty-hint">불러오는 중...</div>';
  try {
    const res = await apiFetch("/api/admin/users");
    const users = (await res.json()).filter((u) => !u.is_owner);
    list.innerHTML = "";
    if (!users.length) {
      list.innerHTML = '<div class="empty-hint">다른 계정이 아직 없습니다</div>';
      return;
    }
    for (const u of users) {
      const row = document.createElement("div");
      row.className = "admin-user-row";
      const label = document.createElement("span");
      label.className = "admin-user-label";
      const name = document.createElement("span");
      name.className = "admin-user-name";
      name.textContent = u.username;
      const meta = document.createElement("span");
      meta.className = "admin-user-meta";
      const joined = u.created_at ? u.created_at.slice(0, 10) : "?";
      meta.textContent = `${joined} 가입 · ${u.login_method} · 메시지 ${u.message_count}개`;
      label.appendChild(name);
      label.appendChild(meta);
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "admin-grant-btn" + (u.ui_dev_granted ? " granted" : "");
      btn.textContent = u.ui_dev_granted ? "유이 권한 있음" : "유이 권한 없음";
      btn.addEventListener("click", async () => {
        try {
          await apiFetch(`/api/admin/ui_dev_grants/${encodeURIComponent(u.username)}`, {
            method: u.ui_dev_granted ? "DELETE" : "POST",
          });
          renderAdminUsers();
        } catch (e) {
          if (e.message !== "unauthorized" && e.message !== "forbidden") console.error(e);
        }
      });
      row.appendChild(label);
      row.appendChild(btn);
      list.appendChild(row);
    }
  } catch (e) {
    if (e.message !== "unauthorized" && e.message !== "forbidden") {
      list.innerHTML = '<div class="empty-hint">불러오지 못했습니다</div>';
      console.error(e);
    }
  }
}

async function renderAdminPersonas() {
  const list = document.getElementById("admin-persona-list");
  list.innerHTML = '<div class="empty-hint">불러오는 중...</div>';
  try {
    const personas = await (await apiFetch("/api/admin/personas")).json();
    list.innerHTML = "";
    for (const p of personas) {
      const card = document.createElement("div");
      card.className = "admin-persona-card";
      const image = p.avatar_url
        ? `<img src="${escapeHtml(p.avatar_url)}" alt="">`
        : `<span>${escapeHtml(p.name[0] || "T")}</span>`;
      card.innerHTML = `<div class="admin-persona-head"><div class="admin-persona-avatar">${image}</div><div><strong>${escapeHtml(displayName(p.name))}</strong><small>${p.owner_username ? ` · ${escapeHtml(p.owner_username)} 소유` : " · 공용"}</small></div></div>`;
      const textarea = document.createElement("textarea");
      textarea.rows = 4;
      textarea.maxLength = 2000;
      textarea.value = p.admin_description || p.description || p.profile_summary || "";
      const actions = document.createElement("div");
      actions.className = "admin-persona-actions";
      const save = document.createElement("button");
      save.type = "button"; save.textContent = "설정 저장";
      save.addEventListener("click", async () => {
        const res = await apiFetch(`/api/admin/personas/${encodeURIComponent(p.name)}`, {method:"PUT", headers:{"Content-Type":"application/json"}, body:JSON.stringify({description:textarea.value})});
        if (!res.ok) alert((await res.json()).detail || "저장 실패"); else save.textContent = "저장됨";
      });
      const upload = document.createElement("button");
      upload.type = "button"; upload.textContent = "이미지 변경";
      const input = document.createElement("input");
      input.type = "file"; input.accept = "image/*"; input.className = "hidden";
      upload.addEventListener("click", () => input.click());
      input.addEventListener("change", async () => {
        if (!input.files[0]) return;
        const data = new FormData(); data.append("file", input.files[0]);
        const res = await apiFetch(`/api/admin/personas/${encodeURIComponent(p.name)}/avatar`, {method:"POST", body:data});
        if (!res.ok) alert((await res.json()).detail || "업로드 실패"); else renderAdminPersonas();
      });
      const remove = document.createElement("button");
      remove.type = "button"; remove.textContent = "이미지 삭제"; remove.className = "danger-subtle";
      remove.addEventListener("click", async () => { await apiFetch(`/api/admin/personas/${encodeURIComponent(p.name)}/avatar`, {method:"DELETE"}); renderAdminPersonas(); });
      const generate = document.createElement("button");
      generate.type = "button"; generate.textContent = "유이에게 이미지 생성 요청";
      generate.addEventListener("click", () => {
        document.getElementById("admin-panel").classList.add("hidden");
        location.hash = "#room=" + encodeURIComponent("유이");
        setTimeout(() => {
          const messageInput = document.getElementById("input");
          messageInput.value = `${p.name}의 프로필 이미지를 GPT로 만들어줘. 현재 설정: ${textarea.value}`;
          messageInput.focus();
        }, 100);
      });
      actions.append(save, upload, generate, remove, input); card.append(textarea, actions); list.appendChild(card);
    }
  } catch (e) { list.innerHTML = '<div class="empty-hint">불러오지 못했습니다</div>'; console.error(e); }
}

document.getElementById("admin-btn").addEventListener("click", () => {
  const panel = document.getElementById("admin-panel");
  if (!panel.classList.contains("hidden")) {
    panel.classList.add("hidden");
    return;
  }
  panel.classList.remove("hidden");
  renderAdminUsers();
  renderAdminPersonas();
});

// ★ 2026-08-26: "사용자가 자신만의 페르소나를 생성하고 수정하거나 대화가
// 가능하게 만들어달라" 요청 — 로그인한 계정이면 누구나(소유자 아니어도)
// 자기만의 페르소나를 만들고, 1:1로 대화하고, 나중에 설정을 고치거나 지울
// 수 있다. worker/persona_worker.py가 이 페르소나들을 별도로 캐시에 합쳐서
// 실제 응답을 생성한다(Notion을 거치지 않음).
let editingPersonaName = null;

function resetMyPersonaForm() {
  editingPersonaName = null;
  document.getElementById("my-persona-name").value = "";
  document.getElementById("my-persona-name").disabled = false;
  document.getElementById("my-persona-desc").value = "";
  document.getElementById("my-persona-submit").textContent = "만들기";
  document.getElementById("my-persona-cancel-edit").classList.add("hidden");
  document.getElementById("my-persona-error").classList.add("hidden");
}

function startEditPersona(p) {
  editingPersonaName = p.name;
  document.getElementById("my-persona-name").value = p.name;
  document.getElementById("my-persona-name").disabled = true;
  document.getElementById("my-persona-desc").value = p.description || "";
  document.getElementById("my-persona-submit").textContent = "수정 저장";
  document.getElementById("my-persona-cancel-edit").classList.remove("hidden");
  document.getElementById("my-persona-error").classList.add("hidden");
}

document.getElementById("my-persona-cancel-edit").addEventListener("click", resetMyPersonaForm);

async function deleteMyPersona(name) {
  if (!confirm(`"${name}"을(를) 삭제할까요? 그동안 나눈 대화 내용도 함께 사라집니다.`)) return;
  try {
    await apiFetch(`/api/my_personas/${encodeURIComponent(name)}`, { method: "DELETE" });
    if (editingPersonaName === name) resetMyPersonaForm();
    await renderMyPersonas();
    await showRoomList();
  } catch (e) {
    if (e.message !== "unauthorized" && e.message !== "forbidden") console.error(e);
  }
}

async function renderMyPersonas() {
  const list = document.getElementById("my-personas-list");
  list.innerHTML = '<div class="empty-hint">불러오는 중...</div>';
  try {
    const res = await apiFetch("/api/my_personas");
    const personas = await res.json();
    list.innerHTML = "";
    if (!personas.length) {
      list.innerHTML = '<div class="empty-hint">아직 만든 페르소나가 없습니다</div>';
    }
    for (const p of personas) {
      const row = document.createElement("div");
      row.className = "my-persona-row";
      const label = document.createElement("span");
      label.textContent = p.name;
      const editBtn = document.createElement("button");
      editBtn.type = "button";
      editBtn.textContent = "수정";
      editBtn.addEventListener("click", () => startEditPersona(p));
      const delBtn = document.createElement("button");
      delBtn.type = "button";
      delBtn.textContent = "삭제";
      delBtn.addEventListener("click", () => deleteMyPersona(p.name));
      row.appendChild(label);
      row.appendChild(editBtn);
      row.appendChild(delBtn);
      list.appendChild(row);
    }
  } catch (e) {
    if (e.message !== "unauthorized" && e.message !== "forbidden") {
      list.innerHTML = '<div class="empty-hint">불러오지 못했습니다</div>';
      console.error(e);
    }
  }
}

document.getElementById("persona-manager-btn").addEventListener("click", () => {
  const panel = document.getElementById("persona-manager-panel");
  if (!panel.classList.contains("hidden")) {
    panel.classList.add("hidden");
    return;
  }
  panel.classList.remove("hidden");
  resetMyPersonaForm();
  renderMyPersonas();
});

document.getElementById("my-persona-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const errorEl = document.getElementById("my-persona-error");
  errorEl.classList.add("hidden");
  const name = document.getElementById("my-persona-name").value.trim();
  const description = document.getElementById("my-persona-desc").value.trim();
  try {
    const res = editingPersonaName
      ? await apiFetch(`/api/my_personas/${encodeURIComponent(editingPersonaName)}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ description }),
        })
      : await apiFetch("/api/my_personas", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name, description }),
        });
    const data = await res.json();
    if (!res.ok) {
      errorEl.textContent = data.detail || "실패했습니다";
      errorEl.classList.remove("hidden");
      return;
    }
    resetMyPersonaForm();
    await renderMyPersonas();
    await showRoomList(); // 새/수정된 페르소나의 1:1 방이 목록에 바로 보이게
  } catch (err) {
    if (err.message !== "unauthorized" && err.message !== "forbidden") {
      errorEl.textContent = "네트워크 오류입니다";
      errorEl.classList.remove("hidden");
      console.error(err);
    }
  }
});

// ★ "툴파들의 성격을 간단하게 확인할 수 있는 프로필 페이지" 요청(2026-08-26) —
// Notion "## 프로필" 섹션(유형·정체성/관계·성격·말투·배경)만 추린 짧은 요약을
// 카드로 나열해서 보여준다. 공개 페르소나 전부 + 내가 만든 페르소나만 온다
// (서버가 그 기준으로 이미 걸러줌).
document.getElementById("profiles-btn").addEventListener("click", async () => {
  const panel = document.getElementById("profiles-panel");
  if (!panel.classList.contains("hidden")) {
    panel.classList.add("hidden");
    return;
  }
  panel.classList.remove("hidden");
  const list = document.getElementById("profiles-list");
  list.innerHTML = '<div class="empty-hint">불러오는 중...</div>';
  try {
    const res = await apiFetch("/api/persona_profiles");
    const profiles = await res.json();
    list.innerHTML = "";
    if (!profiles.length) {
      list.innerHTML = '<div class="empty-hint">아직 페르소나가 없습니다</div>';
    }
    for (const p of profiles) {
      const card = document.createElement("div");
      card.className = "profile-card";
      const avatar = document.createElement("div");
      avatar.className = "profile-card-avatar" + (p.avatar_url ? " has-image" : "");
      if (p.avatar_url) {
        const img = document.createElement("img");
        img.src = p.avatar_url;
        img.alt = `${p.name} 프로필 이미지`;
        avatar.appendChild(img);
      } else {
        avatar.textContent = p.name[0] || "T";
      }
      const content = document.createElement("div");
      content.className = "profile-card-content";
      const title = document.createElement("div");
      title.className = "profile-card-title";
      title.textContent = displayName(p.name) + (p.is_mine ? " · 내가 만듦" : "");
      const body = document.createElement("div");
      body.className = "profile-card-body";
      body.textContent = p.summary;
      content.appendChild(title);
      content.appendChild(body);
      if (amOwner) {
        const edit = document.createElement("button");
        edit.type = "button";
        edit.className = "profile-edit-btn";
        edit.textContent = "수정";
        edit.addEventListener("click", () => {
          if (content.querySelector(".profile-edit-form")) return;
          body.classList.add("hidden");
          edit.classList.add("hidden");
          const form = document.createElement("div");
          form.className = "profile-edit-form";
          const textarea = document.createElement("textarea");
          textarea.rows = 6;
          textarea.maxLength = 2000;
          textarea.value = p.summary === "(아직 프로필 정보가 없습니다)" ? "" : p.summary;
          const actions = document.createElement("div");
          actions.className = "profile-edit-actions";
          const save = document.createElement("button");
          save.type = "button";
          save.textContent = "저장";
          const cancel = document.createElement("button");
          cancel.type = "button";
          cancel.textContent = "취소";
          cancel.addEventListener("click", () => { form.remove(); body.classList.remove("hidden"); edit.classList.remove("hidden"); });
          save.addEventListener("click", async () => {
            const description = textarea.value.trim();
            if (!description) { alert("프로필 설정을 입력해주세요"); return; }
            save.disabled = true;
            const res = await apiFetch(`/api/admin/personas/${encodeURIComponent(p.name)}`, {
              method: "PUT", headers: {"Content-Type": "application/json"}, body: JSON.stringify({description}),
            });
            if (!res.ok) { alert((await res.json()).detail || "저장하지 못했습니다"); save.disabled = false; return; }
            p.summary = description;
            body.textContent = description;
            form.remove();
            body.classList.remove("hidden");
            edit.classList.remove("hidden");
          });
          actions.append(save, cancel);
          form.append(textarea, actions);
          content.appendChild(form);
        });
        content.appendChild(edit);
      }
      card.appendChild(avatar);
      card.appendChild(content);
      list.appendChild(card);
    }
  } catch (e) {
    if (e.message !== "unauthorized" && e.message !== "forbidden") {
      list.innerHTML = '<div class="empty-hint">불러오지 못했습니다</div>';
      console.error(e);
    }
  }
});

// ★ "사용자가 단체톡방 만들기가 가능하게 해달라, 초대할 수 있는 사람들을
// 초대하는 것도 가능하게 해달라" 요청(2026-08-26) — 방 이름 하나만 받으면
// 되는 단순한 입력이라 별도 폼 없이 prompt()로 처리한다. 만든 뒤엔 그 방의
// 참여자 초대 UI(기존 👥 버튼)로 바로 이어서 페르소나를 부를 수 있다.
document.getElementById("new-room-btn").addEventListener("click", async () => {
  const label = prompt("새 채팅방 이름을 입력하세요");
  if (!label || !label.trim()) return;
  try {
    const res = await apiFetch("/api/rooms", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ label: label.trim() }),
    });
    const data = await res.json();
    if (!res.ok) {
      alert(data.detail || "채팅방을 만들지 못했습니다");
      return;
    }
    // ★ showChatView()가 roomsCache에서 제목/초대버튼 표시 여부를 읽는데,
    // 방금 만든 방은 아직 /api/rooms를 다시 안 불러왔으니 캐시에 없다 — 서버가
    // 내려줄 모양 그대로 미리 심어둬서 바로 정상 표시되게 한다.
    roomsCache.set(data.room_id, {
      room_id: data.room_id, label: `👥 ${data.label}`, group_name: null,
      is_group_room: true, is_mine: true, last_message_id: null,
    });
    location.hash = "#room=" + encodeURIComponent(data.room_id);
  } catch (e) {
    if (e.message !== "unauthorized" && e.message !== "forbidden") console.error(e);
  }
});

// ★ "링크 공유해서 읽기만 되게 해달라" 요청(2026-08-25) — 쓰기 불가 방문자는
// 아예 입력창/사진첨부/답장 UI를 숨긴다(서버도 403으로 막지만, UI에서부터
// 안 보이게 해서 혼란을 줄임). 2026-08-26: 로그인 자체가 안 된 방문자(공유
// 링크도 아닌 경우)는 아예 채팅 화면 대신 로그인 화면을 보여준다.
// ★ 2026-08-26: "구글이랑 카카오 로그인 가능하게 해달라" 요청 — 아직 도메인
// 설정이 안 끝나 서버가 비활성 상태(google_login_enabled=false 등)면 버튼을
// 아예 숨긴다. showAuthView()가 나중에(세션 만료 등으로) 다시 불려도 값이
// 유지되게 모듈 전역에 캐시해둔다.
let oauthFlags = { google: false, kakao: false };

function applyOauthButtons() {
  document.getElementById("google-login-btn").classList.toggle("hidden", !oauthFlags.google);
  document.getElementById("kakao-login-btn").classList.toggle("hidden", !oauthFlags.kakao);
}

async function initAuth() {
  let data;
  try {
    const res = await fetch("/api/whoami");
    data = await res.json();
  } catch (e) {
    canWrite = true; // 조회 실패 시 기존 동작(서버가 어차피 막아줌) 유지
    return true;
  }
  canWrite = !!data.can_write;
  myUsername = data.username || null;
  amOwner = !!data.is_owner;
  oauthFlags = { google: !!data.google_login_enabled, kakao: !!data.kakao_login_enabled };
  applyOauthButtons();
  if (!data.logged_in && !data.share_guest && !canWrite) {
    showAuthView();
    return false;
  }
  if (!canWrite) document.body.classList.add("read-only");
  initAccountChip();
  return true;
}

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
  const item = document.createElement("div");
  item.className = "room-item";
  item.tabIndex = 0;
  item.setAttribute("role", "button");
  const isMeta = r.room_id === "group" || r.is_group_room;
  const avatarChar = r.label.replace(/^👥\s*/, "")[0] || "T";
  const roomLabel = isMeta ? r.label.replace(/^👥\s*/, "") : displayName(r.label);
  const unread = r.last_message_id && r.last_message_id > getLastRead(r.room_id);
  // ★ "토론방 대표사진 썸네일" 요청(2026-08-26) — 커스텀 방에 thumbnail_url이
  // 있으면 글자 아바타 대신 그 이미지를 보여준다.
  const avatarInner = r.thumbnail_url
    ? `<img src="${escapeHtml(r.thumbnail_url)}" alt="">`
    : isMeta
      ? '<svg class="room-type-icon" aria-hidden="true"><use href="#icon-users"></use></svg>'
      : escapeHtml(avatarChar);
  item.innerHTML = `
    <div class="avatar${r.thumbnail_url ? " avatar-image" : ""}">${avatarInner}</div>
    <div class="room-info">
      <div class="room-name">${escapeHtml(roomLabel)}${unread ? '<span class="unread-dot"></span>' : ""}</div>
      <div class="room-preview">${r.last_message ? escapeHtml(r.last_message) : "대화를 시작해보세요"}</div>
    </div>
  `;
  const openChat = () => { location.hash = "#room=" + encodeURIComponent(r.room_id); };
  if (listMode === "friends" && !isMeta) {
    item.title = "한 번 클릭해 선택, 더블클릭해 대화하기";
    item.addEventListener("click", () => {
      document.querySelectorAll(".room-item.selected").forEach((el) => el.classList.remove("selected"));
      item.classList.add("selected");
    });
    item.addEventListener("dblclick", openChat);
    const menuBtn = document.createElement("button");
    menuBtn.type = "button";
    menuBtn.className = "friend-more-btn";
    menuBtn.setAttribute("aria-label", `${r.label} 메뉴`);
    menuBtn.textContent = "⋯";
    menuBtn.addEventListener("click", (event) => {
      event.stopPropagation();
      closeFriendMenus();
      const menu = document.createElement("div");
      menu.className = "friend-action-menu";
      item.classList.add("menu-open");
      const addAction = (label, action) => {
        const button = document.createElement("button");
        button.type = "button"; button.textContent = label;
        button.addEventListener("click", (e) => { e.stopPropagation(); closeFriendMenus(); action(); });
        menu.appendChild(button);
      };
      addAction("대화하기", openChat);
      addAction("프로필 보기", () => {
        const panel = document.getElementById("profiles-panel");
        if (panel.classList.contains("hidden")) document.getElementById("profiles-btn").click();
      });
      if (amOwner) addAction("그룹 설정", () => openGroupPicker(item, r));
      item.appendChild(menu);
    });
    item.appendChild(menuBtn);
    item.addEventListener("keydown", (event) => { if (event.key === "Enter") openChat(); });
  } else {
    item.addEventListener("click", openChat);
    item.addEventListener("keydown", (event) => { if (event.key === "Enter" || event.key === " ") openChat(); });
  }
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
let listMode = localStorage.getItem("tulpa_list_mode") === "chats" ? "chats" : "friends";

// ★ "친구 목록이 그룹화돼 있으니 그룹별로 토글해서 목록을 축약하는 기능이
// 있으면 좋겠다" 요청(2026-08-26) — 접은 그룹은 기기별 localStorage에
// 저장해서 새로고침·재방문해도 유지된다.
const COLLAPSED_GROUPS_KEY = "tulpa_collapsed_groups";
let collapsedGroups = new Set(JSON.parse(localStorage.getItem(COLLAPSED_GROUPS_KEY) || "[]"));

function toggleGroupCollapse(key) {
  if (collapsedGroups.has(key)) collapsedGroups.delete(key);
  else collapsedGroups.add(key);
  localStorage.setItem(COLLAPSED_GROUPS_KEY, JSON.stringify([...collapsedGroups]));
  renderCurrentList();
}

function renderCurrentList() {
  const rooms = [...roomsCache.values()];
  const friendsTab = document.getElementById("friends-tab");
  const chatsTab = document.getElementById("chats-tab");
  friendsTab.classList.toggle("active", listMode === "friends");
  chatsTab.classList.toggle("active", listMode === "chats");
  friendsTab.setAttribute("aria-selected", String(listMode === "friends"));
  chatsTab.setAttribute("aria-selected", String(listMode === "chats"));
  document.getElementById("main-view-title").textContent = listMode === "friends" ? "친구" : "채팅";
  roomListEl.innerHTML = "";
  if (listMode === "chats") {
    const chats = rooms
      .filter((r) => r.room_id === "group" || r.is_group_room || r.last_message_id)
      .sort((a, b) => String(b.last_message_at || "").localeCompare(String(a.last_message_at || "")));
    if (!chats.length) {
      roomListEl.innerHTML = '<div class="empty-hint"><strong>아직 대화가 없습니다</strong><br>친구 탭에서 페르소나를 골라 대화를 시작해보세요.</div>';
      return;
    }
    for (const r of chats) roomListEl.appendChild(renderRoomItem(r));
    return;
  }
  const friends = rooms.filter((r) => r.room_id !== "group" && !r.is_group_room);
  if (!friends.length) {
    roomListEl.innerHTML = '<div class="empty-hint">아직 친구가 없습니다</div>';
    return;
  }
  const { groups, orderedKeys } = groupRooms(friends);
  for (const key of orderedKeys) {
    const members = groups.get(key);
    const isCollapsed = collapsedGroups.has(key);
    const header = document.createElement("button");
    header.type = "button";
    header.className = "group-header";
    header.setAttribute("aria-expanded", String(!isCollapsed));
    header.innerHTML = `
      <span class="group-toggle-arrow">${isCollapsed ? "▸" : "▾"}</span>
      <span class="group-header-label">${escapeHtml(key)}</span>
      <span class="group-count">${members.length}</span>
    `;
    header.addEventListener("click", () => toggleGroupCollapse(key));
    roomListEl.appendChild(header);
    if (!isCollapsed) {
      for (const r of members) roomListEl.appendChild(renderRoomItem(r));
    }
  }
}

function setListMode(mode) {
  listMode = mode;
  localStorage.setItem("tulpa_list_mode", mode);
  renderCurrentList();
}

document.getElementById("friends-tab").addEventListener("click", () => setListMode("friends"));
document.getElementById("chats-tab").addEventListener("click", () => setListMode("chats"));

// ★ "그룹 이름을 매번 직접 타이핑하지 말고, 이미 있는 그룹 목록에서 고르고
// 없으면 새로 만들게 해달라" 요청(2026-08-26) — "그룹 설정" 클릭 시 바로
// prompt()를 띄우던 걸, 기존 그룹 목록 + "그룹 없음" + "새 그룹 만들기"를
// 고르는 작은 메뉴로 바꾼다.
async function setPersonaGroup(r, value) {
  const res = await apiFetch(`/api/admin/personas/${encodeURIComponent(r.room_id)}/group`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ group_name: value }),
  });
  if (!res.ok) { alert((await res.json()).detail || "그룹을 바꾸지 못했습니다"); return; }
  await showRoomList();
}

function openGroupPicker(item, r) {
  const menu = document.createElement("div");
  menu.className = "friend-action-menu";
  item.classList.add("menu-open");
  const existingGroups = [...new Set(
    [...roomsCache.values()].map((x) => x.group_name).filter((g) => g)
  )].sort((a, b) => a.localeCompare(b, "ko"));
  const addPickerAction = (label, action) => {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = label;
    button.addEventListener("click", (e) => { e.stopPropagation(); closeFriendMenus(); action(); });
    menu.appendChild(button);
  };
  for (const g of existingGroups) {
    addPickerAction(g === r.group_name ? `✓ ${g}` : g, () => setPersonaGroup(r, g));
  }
  addPickerAction("그룹 없음으로 설정", () => setPersonaGroup(r, ""));
  addPickerAction("+ 새 그룹 만들기", () => {
    const value = prompt(`${r.label}의 새 그룹 이름을 입력하세요.`, "");
    if (value === null || !value.trim()) return;
    setPersonaGroup(r, value.trim());
  });
  item.appendChild(menu);
}

function closeFriendMenus() {
  document.querySelectorAll(".friend-action-menu").forEach((el) => el.remove());
  document.querySelectorAll(".room-item.menu-open").forEach((el) => el.classList.remove("menu-open"));
}

document.addEventListener("click", (event) => {
  if (!event.target.closest(".friend-more-btn") && !event.target.closest(".friend-action-menu")) {
    closeFriendMenus();
  }
});

async function showRoomList() {
  currentRoom = null;
  if (pollTimer) clearTimeout(pollTimer);
  authView.classList.add("hidden");
  chatView.classList.add("hidden");
  roomListView.classList.remove("hidden");
  try {
    const res = await apiFetch("/api/rooms");
    const rooms = await res.json();
    roomsCache = new Map(rooms.map((r) => [r.room_id, r]));
    if (!rooms.length) {
      roomListEl.innerHTML = '<div class="empty-hint">아직 페르소나가 없습니다</div>';
      return;
    }
    renderCurrentList();
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

async function showChatView(roomId) {
  currentRoom = roomId;
  lastId = 0;
  setReplyTarget(null);
  messagesEl.innerHTML = "";
  roomListView.classList.add("hidden");
  chatView.classList.remove("hidden");
  // ★ 새로고침·직접 URL 접속처럼 showRoomList()를 거치지 않고 바로 이
  // 방으로 들어온 경우 roomsCache가 비어 있어 그룹 회의방 여부(공지 배너,
  // 참여자 버튼, "(가상)" 라벨)를 전부 잘못 판단하는 버그가 있었다
  // (2026-08-26 "개발 단체방 공지사항 안 뜨는" 문제의 원인) — 캐시에
  // 없으면 방 목록을 먼저 받아와 채운다.
  if (!roomsCache.has(roomId)) {
    try {
      const res = await apiFetch("/api/rooms");
      const rooms = await res.json();
      roomsCache = new Map(rooms.map((r) => [r.room_id, r]));
    } catch (e) {
      if (e.message !== "unauthorized" && e.message !== "forbidden") console.error(e);
    }
  }
  // ★ 그룹 회의방(예: "예술가부흥프로젝트")은 페르소나 이름이 아니라 방
  // 제목이므로 (가상) 라벨을 안 붙인다 — roomsCache로 room_id가 그룹
  // 회의방인지 확인한다(캐시에도 없으면 존재하지 않는 방일 수 있으니
  // 안전하게 페르소나 이름으로 간주).
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
  // ★ "토론방 대표사진" 요청(2026-08-26) — 내가 만든 커스텀 방(custom_)에서만
  // 썸네일 변경 버튼을 보여준다.
  const isMyCustomRoom = roomId.startsWith("custom_") && canWrite && (amOwner || (cached && cached.is_mine));
  document.getElementById("thumbnail-btn").classList.toggle("hidden", !isMyCustomRoom);
  if (cached && cached.last_message_id) markRoomRead(roomId, cached.last_message_id);
  loadRoomNotice(roomId, isGroupMeetingRoom);
  poll();
}

// ★ "채팅창에 카카오톡처럼 공지사항이 보였으면 좋겠다, 그 방 대화를 토대로
// 업데이트 내용을 하루하루 요약해서 공지해달라" 요청(2026-08-26) — 워커가
// sync_room_notices()로 채워둔 최신 공지를 그룹/커스텀 방 상단에 고정
// 배너로 보여준다. 1:1 방·전체 채팅방은 대상이 아니라 조용히 숨긴다.
async function loadRoomNotice(roomId, isGroupMeetingRoom) {
  const notice = document.getElementById("room-notice");
  const noticeText = document.getElementById("room-notice-text");
  const noticeToggle = document.getElementById("room-notice-toggle");
  notice.classList.remove("expanded");
  noticeToggle.classList.add("hidden");
  noticeToggle.textContent = "더보기";
  noticeToggle.setAttribute("aria-expanded", "false");
  if (!isGroupMeetingRoom) {
    notice.classList.add("hidden");
    return;
  }
  try {
    const res = await apiFetch(`/api/rooms/${encodeURIComponent(roomId)}/notice`);
    const data = await res.json();
    if (data && data.content) {
      noticeText.textContent = data.content;
      notice.classList.remove("hidden");
      requestAnimationFrame(() => {
        const isOverflowing = noticeText.scrollHeight > noticeText.clientHeight + 1;
        noticeToggle.classList.toggle("hidden", !isOverflowing);
      });
    } else {
      notice.classList.add("hidden");
    }
  } catch (e) {
    notice.classList.add("hidden");
    if (e.message !== "unauthorized" && e.message !== "forbidden") console.error(e);
  }
}

document.getElementById("room-notice-toggle").addEventListener("click", () => {
  const notice = document.getElementById("room-notice");
  const toggle = document.getElementById("room-notice-toggle");
  const expanded = notice.classList.toggle("expanded");
  toggle.textContent = expanded ? "접기" : "더보기";
  toggle.setAttribute("aria-expanded", String(expanded));
});

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
    const res = await apiFetch(`/api/rooms/${encodeURIComponent(currentRoom)}/members`);
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
    // ★ 초대 후보 목록은 쓰기 권한이 있고, "소유자이거나 내가 만든 방"일
    // 때만 보여준다(2026-08-26) — 공유 Notion 그룹 회의방은 소유자만
    // 초대할 수 있게 서버에서 막아뒀으므로, 어차피 실패할 초대 버튼을
    // non-owner에게 보여주지 않는다(눌렀다가 방 밖으로 튕겨나가는 걸 방지).
    const cachedRoom = roomsCache.get(currentRoom);
    const canInviteHere = canWrite && (amOwner || (cachedRoom && cachedRoom.is_mine));
    inviteSection.classList.toggle("hidden", !canInviteHere);
    if (canInviteHere) {
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
    await apiFetch(`/api/rooms/${encodeURIComponent(currentRoom)}/invite`, {
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

// ★ "토론방 대표사진을 썸네일로 보이게 해달라" 요청(2026-08-26) — 🖼️ 버튼은
// 내가 만든 커스텀 방에서만 보인다(showChatView에서 토글). 업로드 즉시
// 방 목록 캐시도 갱신해서 방 목록으로 돌아갔을 때 바로 반영되게 한다.
const thumbnailInput = document.getElementById("thumbnail-input");
document.getElementById("thumbnail-btn").addEventListener("click", () => thumbnailInput.click());
thumbnailInput.addEventListener("change", async () => {
  const file = thumbnailInput.files[0];
  thumbnailInput.value = "";
  if (!file || !currentRoom) return;
  const formData = new FormData();
  formData.append("file", file);
  try {
    const res = await apiFetch(`/api/rooms/${encodeURIComponent(currentRoom)}/thumbnail`, {
      method: "POST",
      body: formData,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      alert(err.detail || "대표사진 업로드 실패");
      return;
    }
    const { thumbnail_url } = await res.json();
    const cached = roomsCache.get(currentRoom);
    if (cached) cached.thumbnail_url = thumbnail_url;
  } catch (e) {
    if (e.message !== "unauthorized" && e.message !== "forbidden") {
      console.error(e);
      alert("대표사진 업로드 실패");
    }
  }
});

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
  // ★ 2026-08-26: 다중 계정 로그인 전에는 sender==='user' 하나로 "내 메시지"를
  // 판별했다. 이제 여러 사람이 같은 방에 쓸 수 있어 서버가 내려주는
  // is_persona로 페르소나 여부를 판별하고, 사람 메시지 중에서도 "나"(현재
  // 로그인 계정)와 "다른 사람"을 구분해서 보여준다.
  const isPersona = !!m.is_persona;
  const isMine = !isPersona && m.sender === myUsername;
  const el = document.createElement("div");
  el.className = "msg " + (isPersona ? "msg-persona" : isMine ? "msg-user" : "msg-other");
  if (!isMine) {
    const avatar = document.createElement(m.avatar_url ? "img" : "div");
    avatar.className = "message-avatar";
    avatar.title = `${isPersona ? displayName(m.sender) : m.sender} 프로필`;
    if (m.avatar_url) {
      avatar.src = m.avatar_url;
      avatar.alt = "";
      avatar.loading = "lazy";
    } else {
      avatar.textContent = (isPersona ? displayName(m.sender) : m.sender).trim().charAt(0) || "?";
    }
    if (isPersona && canWrite) {
      avatar.classList.add("message-avatar-clickable");
      avatar.title += " · 탭해서 답장";
      avatar.addEventListener("click", () => setReplyTarget(m.sender));
    }
    el.appendChild(avatar);
  }
  const sender = document.createElement("div");
  sender.className = "sender";
  sender.textContent = isPersona ? displayName(m.sender) : isMine ? "나" : m.sender;
  const cached = roomsCache.get(currentRoom);
  const isMetaRoom = currentRoom === "group" || (cached && cached.is_group_room);
  if (isPersona && isMetaRoom && canWrite) {
    // 그룹/회의방에서만 "답장" 대상 지정이 의미가 있다(1:1 방은 이미 그 한
    // 명뿐이라 필요 없음). 페르소나에게만 답장 가능 — 다른 사람 메시지는
    // 답장 대상이 아니다.
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
    const res = await apiFetch(`/api/messages?room_id=${encodeURIComponent(currentRoom)}&since_id=${lastId}`);
    const messages = await res.json();
    for (const m of messages) {
      appendMessage(m);
      lastId = m.id;
    }
    if (messages.length) markRoomRead(currentRoom, lastId);
  } catch (e) {
    if (e.message === "unauthorized" || e.message === "forbidden") return; // apiFetch가 이미 처리하고 돌려보냄 — 폴링 중단
    console.error(e);
  }
  pollTimer = setTimeout(poll, 2000);
}

async function sendMessage(content) {
  if (!currentRoom || !content) return;
  try {
    await apiFetch("/api/messages", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content, room_id: currentRoom, reply_to: replyTarget }),
    });
  } catch (e) {
    if (e.message !== "unauthorized" && e.message !== "forbidden") console.error(e);
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
    const res = await apiFetch("/api/upload", { method: "POST", body: formData });
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

// ★ "처음 사용하는 사람들도 기능을 알 수 있게 도움말이 있으면 좋겠다"
// 요청(2026-08-26) — 로그인 화면·방 목록 어디서나 열 수 있는 전체 화면
// 오버레이. 순수 정적 안내문이라 서버 호출 없음.
function toggleHelp(show) {
  document.getElementById("help-overlay").classList.toggle("hidden", !show);
}
document.getElementById("help-btn").addEventListener("click", () => toggleHelp(true));
document.getElementById("help-btn-auth").addEventListener("click", () => toggleHelp(true));
document.getElementById("help-close-btn").addEventListener("click", () => toggleHelp(false));

async function route() {
  const room = parseRoomFromHash();
  if (room) {
    await showChatView(room);
  } else {
    await showRoomList();
  }
}

window.addEventListener("hashchange", route);
initAuth().then((ok) => {
  if (ok) route();
});
