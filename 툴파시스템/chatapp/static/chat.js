let lastId = 0;
const messagesEl = document.getElementById("messages");

async function fetchPersonas() {
  try {
    const res = await fetch("/api/personas");
    const personas = await res.json();
    document.getElementById("personas").textContent = personas.length
      ? "참여자: " + personas.join(", ")
      : "아직 페르소나가 없습니다 (워커가 Notion에서 동기화하기 전)";
  } catch (e) {
    console.error(e);
  }
}

function appendMessage(m) {
  const el = document.createElement("div");
  el.className = "msg " + (m.sender === "user" ? "msg-user" : "msg-persona");
  const sender = document.createElement("div");
  sender.className = "sender";
  sender.textContent = m.sender === "user" ? "나" : m.sender;
  const body = document.createElement("div");
  body.className = "body";
  body.textContent = m.content;
  el.appendChild(sender);
  el.appendChild(body);
  messagesEl.appendChild(el);
  el.scrollIntoView({ behavior: "smooth", block: "end" });
}

async function poll() {
  try {
    const res = await fetch(`/api/messages?since_id=${lastId}`);
    const messages = await res.json();
    for (const m of messages) {
      appendMessage(m);
      lastId = m.id;
    }
  } catch (e) {
    console.error(e);
  }
  setTimeout(poll, 2000);
}

document.getElementById("composer").addEventListener("submit", async (e) => {
  e.preventDefault();
  const input = document.getElementById("input");
  const content = input.value.trim();
  if (!content) return;
  input.value = "";
  try {
    await fetch("/api/messages", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content }),
    });
  } catch (e) {
    console.error(e);
  }
});

fetchPersonas();
poll();
