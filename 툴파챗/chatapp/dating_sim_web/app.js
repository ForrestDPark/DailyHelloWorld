const $ = (id) => document.getElementById(id);

async function api(url, options = {}) {
  const response = await fetch(url, {
    credentials: "same-origin",
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  if (response.status === 401) {
    location.href = "/";
    throw new Error("로그인이 필요합니다");
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || "요청을 처리하지 못했습니다");
  return data;
}

function showView(name) {
  for (const id of ["map-view", "scene-view", "ending-view", "loading-view"]) {
    $(id).classList.toggle("hidden", id !== name);
  }
}

function renderHud(state) {
  $("hud-day").textContent = `DAY ${state.day} / ${state.total_days}`;
  $("affection-bar").style.width = `${Math.max(0, Math.min(100, state.affection))}%`;
}

function renderMap(state) {
  const list = $("map-locations");
  list.replaceChildren();
  state.locations.forEach((location) => {
    const tile = document.createElement("button");
    tile.type = "button";
    tile.className = "map-tile";
    tile.innerHTML = `<span class="map-tile-emoji">${location.emoji}</span><span>${location.label}</span>`;
    tile.addEventListener("click", () => visitLocation(location.id));
    list.append(tile);
  });
  showView("map-view");
}

// ★ 2026-09-15: "고전 시뮬레이션 도트 게임 느낌" 요청 — 옛날 RPG 대사창처럼
// 한 글자씩 나타나는 타자기 효과. 클릭하면 즉시 전체 문장을 보여주고,
// 이미 다 보여준 상태에서 누르면 다음 줄로 넘어간다.
let typewriterTimer = null;
let sceneLines = [];
let sceneLineIndex = 0;
let sceneChoices = [];

function stopTypewriter() {
  if (typewriterTimer) {
    clearInterval(typewriterTimer);
    typewriterTimer = null;
  }
}

function typeLine(text) {
  stopTypewriter();
  const el = $("dialogue-text");
  el.textContent = "";
  $("dialogue-next").classList.add("hidden");
  $("choice-list").classList.add("hidden");
  let i = 0;
  typewriterTimer = setInterval(() => {
    i += 1;
    el.textContent = text.slice(0, i);
    if (i >= text.length) {
      stopTypewriter();
      onLineFullyShown();
    }
  }, 22);
}

function onLineFullyShown() {
  const isLastLine = sceneLineIndex >= sceneLines.length - 1;
  if (isLastLine && sceneChoices.length) {
    renderChoices();
  } else {
    $("dialogue-next").classList.remove("hidden");
  }
}

function advanceLine() {
  if (typewriterTimer) {
    // 타자기 도중 클릭하면 그 줄을 즉시 완성해서 보여준다.
    stopTypewriter();
    $("dialogue-text").textContent = sceneLines[sceneLineIndex];
    onLineFullyShown();
    return;
  }
  if (sceneLineIndex < sceneLines.length - 1) {
    sceneLineIndex += 1;
    typeLine(sceneLines[sceneLineIndex]);
  }
}

function renderChoices() {
  const list = $("choice-list");
  list.replaceChildren();
  sceneChoices.forEach((choice, index) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "choice-button";
    button.innerHTML = `<span class="choice-cursor">▶</span>${choice.text}`;
    button.addEventListener("click", () => chooseOption(index));
    list.append(button);
  });
  list.classList.remove("hidden");
}

function renderScene(state) {
  sceneLines = state.scene.lines;
  sceneChoices = state.scene.choices;
  sceneLineIndex = 0;
  $("speaker-name").textContent = state.character_name;
  showView("scene-view");
  typeLine(sceneLines[0]);
}

function renderEnding(state) {
  $("ending-title").textContent = state.ending.title;
  $("ending-text").textContent = state.ending.lines.join(" ");
  showView("ending-view");
}

function render(state) {
  renderHud(state);
  if (state.completed) {
    renderEnding(state);
  } else if (state.scene) {
    renderScene(state);
  } else {
    renderMap(state);
  }
}

async function loadState() {
  showView("loading-view");
  try {
    render(await api("/api/dating-sim/state"));
  } catch (e) {
    $("loading-view").querySelector("p").textContent = e.message;
  }
}

async function visitLocation(locationId) {
  try {
    render(await api("/api/dating-sim/visit", { method: "POST", body: JSON.stringify({ location: locationId }) }));
  } catch (e) {
    alert(e.message);
  }
}

async function chooseOption(choiceIndex) {
  try {
    render(await api("/api/dating-sim/choose", { method: "POST", body: JSON.stringify({ choice_index: choiceIndex }) }));
  } catch (e) {
    alert(e.message);
  }
}

async function restart() {
  if (!confirm("처음부터 다시 시작할까요? 지금까지의 호감도는 사라집니다.")) return;
  try {
    render(await api("/api/dating-sim/restart", { method: "POST" }));
  } catch (e) {
    alert(e.message);
  }
}

$("dialogue-next").addEventListener("click", advanceLine);
document.getElementById("scene-view").addEventListener("click", (event) => {
  if (event.target.closest(".choice-button")) return;
  if (!$("choice-list").classList.contains("hidden")) return;
  advanceLine();
});
$("restart-btn").addEventListener("click", restart);

loadState();
