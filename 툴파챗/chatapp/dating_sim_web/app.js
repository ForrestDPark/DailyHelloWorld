const $ = (id) => document.getElementById(id);
const bookId = new URLSearchParams(location.search).get("book");
const storyId = bookId && /^[0-9a-f]{20}$/.test(bookId) ? `book:${bookId}` : null;
let latestState = null;
let listeningMode = false;
let speechSequence = 0;
let audioManifest = {};
const recordedAudio = new Audio();
let pendingPlaybackResolve = null;
let choiceInFlight = false;
let mapOpeningText = "";
let sceneCharacterImage = "";

function locationBackdrop(location) {
  if (["park", "walk"].includes(location)) return "/dating-sim/static/pixel-park.png";
  if (["school", "first"].includes(location)) return "/dating-sim/static/pixel-school.png";
  return "/dating-sim/static/pixel-cafe.png";
}

function openingBackdrop(opening, day) {
  const normalized = String(opening || "").replace(/\s+/g, " ");
  const isMessageArrival = /メッセージ|メール|返事|메시지|문자|답장|写真.{0,80}届|사진.{0,80}도착/i.test(normalized);
  if (isMessageArrival) return "/dating-sim/static/pixel-message.png";
  return [
    "/dating-sim/static/pixel-cafe.png",
    "/dating-sim/static/pixel-park.png",
    "/dating-sim/static/pixel-school.png",
  ][(Math.max(1, Number(day) || 1) - 1) % 3];
}

function storyQuery() {
  return storyId ? `?story_id=${encodeURIComponent(storyId)}` : "";
}

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
  for (const id of ["map-view", "scene-view", "result-view", "ending-view", "loading-view"]) {
    $(id).classList.toggle("hidden", id !== name);
  }
  $("listening-controls").classList.toggle("hidden", name === "loading-view");
}

function renderHud(state) {
  latestState = state;
  $("hud-title").textContent = "미연시";
  $("hud-day").textContent = `DAY ${state.day} / ${state.total_days}`;
  $("affection-value").textContent = state.affection;
  $("affection-value").parentElement.setAttribute("aria-label", `호감도 ${state.affection}점`);
  $("affection-bar").style.width = `${Math.max(0, Math.min(100, state.affection))}%`;
}

function renderMap(state) {
  if (!recordedAudio.paused || window.speechSynthesis?.speaking) stopListening({ turnOff: false });
  $("stage").dataset.location = "map";
  $("stage").dataset.day = state.day;
  const hint = document.querySelector(".map-hint");
  mapOpeningText = state.day_opening || "오늘 어떤 일이 일어날까?";
  $("intro-art-image").src = openingBackdrop(mapOpeningText, state.day);
  renderAnnotatedText(hint, mapOpeningText);
  const list = $("map-locations");
  list.replaceChildren();
  state.locations.forEach((location) => {
    const tile = document.createElement("button");
    tile.type = "button";
    tile.className = "map-tile";
    const emoji = document.createElement("span");
    emoji.className = "map-tile-emoji";
    emoji.textContent = location.emoji;
    const label = document.createElement("span");
    label.textContent = location.action || location.label;
    tile.append(emoji, label);
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

function plainText(text) {
  return text.replace(/\[([^\]|]+)\|([^\]]+)\]/g, "$1");
}

function japaneseText(text) {
  const surface = plainText(text || "");
  return surface.split("\n")
    .filter((line) => /[\u3040-\u30ff\u3400-\u9fff]/.test(line))
    .join("。")
    .trim();
}

function japaneseVoice(role = "female") {
  const voices = window.speechSynthesis?.getVoices?.() || [];
  const japanese = voices.filter((voice) => /^ja[-_]/i.test(voice.lang));
  const female = /Kyoko|Nanami|Hina|Haruka|Sayaka|Ayumi|女性|Female|女/i;
  const male = /Otoya|Otohiko|Ichiro|Daisuke|男性|Male|男/i;
  if (role === "female") {
    return japanese.find((voice) => female.test(voice.name)) ||
      japanese.find((voice) => !male.test(voice.name)) || japanese[0] || null;
  }
  return japanese.find((voice) => male.test(voice.name)) || japanese[0] || null;
}

function updateListeningControls(status = listeningMode ? "듣는 중" : "꺼짐") {
  const supported = Object.values(audioManifest).some((clips) => Object.keys(clips || {}).length > 0) ||
    ("speechSynthesis" in window && "SpeechSynthesisUtterance" in window);
  $("listening-toggle").disabled = !supported;
  $("listening-replay").disabled = !supported;
  $("listening-toggle").classList.toggle("active", listeningMode);
  $("listening-toggle").setAttribute("aria-pressed", String(listeningMode));
  $("listening-toggle").textContent = listeningMode ? "듣기 켜짐" : "일본어 듣기";
  $("listening-stop").disabled = !supported || !listeningMode;
  $("listening-status").textContent = supported ? status : "이 기기에서는 지원되지 않음";
}

function stopListening({ turnOff = true } = {}) {
  speechSequence += 1;
  recordedAudio.onplay = null;
  recordedAudio.onended = null;
  recordedAudio.onerror = null;
  recordedAudio.pause();
  recordedAudio.removeAttribute("src");
  recordedAudio.load();
  window.speechSynthesis?.cancel();
  if (pendingPlaybackResolve) pendingPlaybackResolve();
  if (turnOff) listeningMode = false;
  updateListeningControls(turnOff ? "꺼짐" : "대기 중");
  $("portrait").classList.remove("speaking");
}

function playStandalone(text, role, status) {
  text = japaneseText(text);
  if (!text || !listeningMode) return Promise.resolve();
  const sequence = ++speechSequence;
  const recordedUrl = audioManifest[role]?.[text];
  return new Promise((resolve) => {
    let settled = false;
    const finish = () => {
      if (settled) return;
      settled = true;
      pendingPlaybackResolve = null;
      $("portrait").classList.remove("speaking");
      resolve();
    };
    pendingPlaybackResolve = finish;
    const deviceFallback = () => {
      if (!("speechSynthesis" in window) || !("SpeechSynthesisUtterance" in window)) {
        finish();
        return;
      }
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.lang = "ja-JP";
      utterance.rate = role === "female" ? 0.9 : 0.86;
      utterance.pitch = role === "female" ? 1.18 : 0.92;
      const voice = japaneseVoice(role);
      if (voice) utterance.voice = voice;
      utterance.onstart = () => {
        if (sequence !== speechSequence) return finish();
        updateListeningControls(`${status} · 기기 음성`);
        $("portrait").classList.toggle("speaking", role === "female");
      };
      utterance.onend = finish;
      utterance.onerror = finish;
      window.speechSynthesis.speak(utterance);
    };
    if (!recordedUrl) {
      deviceFallback();
      return;
    }
    recordedAudio.src = recordedUrl;
    recordedAudio.onplay = () => {
      if (sequence !== speechSequence) return finish();
      updateListeningControls(`${status} · OpenAI 생성 음성`);
      $("portrait").classList.toggle("speaking", role === "female");
    };
    recordedAudio.onended = finish;
    recordedAudio.onerror = () => {
      recordedAudio.onerror = null;
      deviceFallback();
    };
    recordedAudio.play().catch(() => {
      if (recordedAudio.onerror) {
        recordedAudio.onerror = null;
        deviceFallback();
      }
    });
  });
}

async function playMapOpening() {
  const japaneseOnly = (mapOpeningText || "").split("\n")
    .filter((line) => /[\u3040-\u30ff\u3400-\u9fff]/.test(line)).join("\n");
  const quote = japaneseOnly.match(/^(.*?)「(.+?)」(.*)$/s);
  if (!quote) {
    return playStandalone(mapOpeningText, "male", "주인공 독백 재생 중");
  }
  if (quote[1].trim()) await playStandalone(quote[1], "male", "주인공 독백 재생 중");
  if (listeningMode) await playStandalone(quote[2], "female", "메시지 음성 재생 중");
  if (listeningMode && quote[3].trim()) {
    await playStandalone(quote[3], "male", "주인공 독백 재생 중");
  }
}

function finishSpokenLine(sequence) {
  if (sequence !== speechSequence || !listeningMode) return;
  $("portrait").classList.remove("speaking");
  updateListeningControls(
    sceneLineIndex < sceneLines.length - 1 ? "대사창을 눌러 계속" : "선택지를 골라주세요"
  );
}

function speakWithDevice(text, line, sequence, fallback = false) {
  if (!("speechSynthesis" in window) || !("SpeechSynthesisUtterance" in window)) {
    stopListening();
    updateListeningControls("음성을 재생하지 못했어요");
    return;
  }
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = "ja-JP";
  const role = line.speaker === "narrator" ? "male" : "female";
  utterance.rate = role === "female" ? 0.9 : 0.86;
  utterance.pitch = role === "female" ? 1.18 : 0.92;
  const voice = japaneseVoice(role);
  if (voice) utterance.voice = voice;
  utterance.onstart = () => {
    if (sequence !== speechSequence) return;
    updateListeningControls(fallback ? "기기 음성으로 재생 중" : "기기 음성 재생 중");
    $("portrait").classList.toggle("speaking", line.speaker !== "narrator");
  };
  utterance.onend = () => finishSpokenLine(sequence);
  utterance.onerror = () => {
    if (sequence !== speechSequence) return;
    stopListening();
    updateListeningControls("음성을 재생하지 못했어요");
  };
  window.speechSynthesis.speak(utterance);
}

function speakCurrentLine() {
  if (!listeningMode || typewriterTimer || !sceneLines.length) return;
  const line = sceneLines[sceneLineIndex];
  const text = japaneseText(typeof line === "string" ? line : line.text);
  if (!text) {
    if (sceneLineIndex < sceneLines.length - 1) advanceLine();
    return;
  }
  const sequence = ++speechSequence;
  const role = line.speaker === "narrator" ? "male" : "female";
  const recordedUrl = audioManifest[role]?.[text];
  if (!recordedUrl) {
    speakWithDevice(text, line, sequence);
    return;
  }
  window.speechSynthesis?.cancel();
  recordedAudio.src = recordedUrl;
  recordedAudio.onplay = () => {
    if (sequence !== speechSequence) return;
    updateListeningControls("OpenAI 생성 음성 재생 중");
    $("portrait").classList.toggle("speaking", line.speaker !== "narrator");
  };
  recordedAudio.onended = () => finishSpokenLine(sequence);
  recordedAudio.onerror = () => {
    if (sequence !== speechSequence || !listeningMode) return;
    recordedAudio.onerror = null;
    speakWithDevice(text, line, sequence, true);
  };
  recordedAudio.play().catch(() => {
    if (sequence === speechSequence && listeningMode && recordedAudio.onerror) {
      recordedAudio.onerror = null;
      speakWithDevice(text, line, sequence, true);
    }
  });
}

async function loadAudioManifest() {
  try {
    const response = await fetch("/dating-sim/audio/manifest.json", {
      credentials: "same-origin", cache: "no-store",
    });
    if (!response.ok) return;
    const manifest = await response.json();
    audioManifest = manifest.clips || {};
  } catch (_error) {
    audioManifest = {};
  }
  updateListeningControls();
}

function renderAnnotatedText(element, text) {
  element.replaceChildren();
  const pattern = /\[([^\]|]+)\|([^\]]+)\]|\n/g;
  let cursor = 0;
  for (const match of text.matchAll(pattern)) {
    if (match.index > cursor) element.append(document.createTextNode(text.slice(cursor, match.index)));
    if (match[0] === "\n") {
      element.append(document.createElement("br"));
    } else {
      const ruby = document.createElement("ruby");
      ruby.append(document.createTextNode(match[1]));
      const rt = document.createElement("rt");
      rt.textContent = match[2];
      ruby.append(rt);
      element.append(ruby);
    }
    cursor = match.index + match[0].length;
  }
  if (cursor < text.length) element.append(document.createTextNode(text.slice(cursor)));
}

function stopTypewriter() {
  if (typewriterTimer) {
    clearInterval(typewriterTimer);
    typewriterTimer = null;
  }
}

function typeLine(text) {
  stopTypewriter();
  const line = typeof text === "string" ? { speaker: "character", text } : text;
  text = line.text;
  const narrator = line.speaker === "narrator";
  $("speaker-name").textContent = narrator ? "主人公 · 나" : (latestState?.character_name || "");
  $("portrait").classList.toggle("narrator", narrator);
  $("portrait-image").src = narrator
    ? locationBackdrop($("stage").dataset.location)
    : sceneCharacterImage;
  const el = $("dialogue-text");
  el.textContent = "";
  $("dialogue-next").classList.add("hidden");
  $("choice-list").classList.add("hidden");
  $("portrait").classList.toggle("speaking", !narrator);
  const visibleText = plainText(text);
  let i = 0;
  typewriterTimer = setInterval(() => {
    i += 1;
    el.textContent = visibleText.slice(0, i);
    if (i >= visibleText.length) {
      stopTypewriter();
      renderAnnotatedText(el, text);
      $("portrait").classList.remove("speaking");
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
  if (listeningMode) speakCurrentLine();
}

function advanceLine() {
  if (!recordedAudio.paused || window.speechSynthesis?.speaking) stopListening({ turnOff: false });
  if (typewriterTimer) {
    // 타자기 도중 클릭하면 그 줄을 즉시 완성해서 보여준다.
    stopTypewriter();
    const line = sceneLines[sceneLineIndex];
    renderAnnotatedText($("dialogue-text"), typeof line === "string" ? line : line.text);
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
    const cursor = document.createElement("span");
    cursor.className = "choice-cursor";
    cursor.textContent = "▶";
    const label = document.createElement("span");
    renderAnnotatedText(label, choice.text);
    button.append(cursor, label);
    button.addEventListener("click", () => chooseOption(index));
    list.append(button);
  });
  list.classList.remove("hidden");
}

function renderScene(state) {
  sceneLines = state.scene.lines;
  sceneChoices = state.scene.choices;
  sceneLineIndex = 0;
  $("stage").dataset.location = state.scene.location;
  $("stage").dataset.day = state.day;
  sceneCharacterImage = state.scene.character_image || state.character_image || "";
  $("portrait-image").src = sceneCharacterImage;
  showView("scene-view");
  updateListeningControls(listeningMode ? "대기 중" : "꺼짐");
  typeLine(sceneLines[0]);
}

function renderChoiceResult(state) {
  const delta = state.choice_result.affection_delta;
  $("result-speaker-name").textContent = state.character_name;
  $("stage").dataset.location = state.choice_result.location || "result";
  $("stage").dataset.day = state.day;
  $("result-portrait-image").src = state.choice_result.character_image || state.character_image || "";
  renderAnnotatedText($("result-text"), state.choice_result.line);
  $("result-affection").textContent = `${delta > 0 ? "+" : ""}${delta} · 현재 호감도 ${state.affection}`;
  showView("result-view");
  if (listeningMode) {
    playStandalone(state.choice_result.line, "female", `${state.character_name} 대사 재생 중`)
      .then(() => updateListeningControls("다음 장면을 눌러 계속"));
  }
}

function renderEnding(state) {
  $("ending-title").textContent = state.ending.title;
  renderAnnotatedText($("ending-text"), state.ending.lines.join("\n"));
  $("ending-speaker-name").textContent = state.character_name;
  $("ending-portrait-image").src = state.character_image || "";
  showView("ending-view");
}

function render(state) {
  renderHud(state);
  if (state.choice_result) {
    renderChoiceResult(state);
  } else if (state.completed) {
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
    render(await api(`/api/dating-sim/state${storyQuery()}`));
  } catch (e) {
    $("loading-view").querySelector("p").textContent = e.message;
  }
}

async function visitLocation(locationId) {
  if (!recordedAudio.paused || window.speechSynthesis?.speaking) stopListening({ turnOff: false });
  try {
    render(await api("/api/dating-sim/visit", { method: "POST", body: JSON.stringify({ location: locationId, story_id: storyId }) }));
  } catch (e) {
    alert(e.message);
  }
}

async function chooseOption(choiceIndex) {
  if (choiceInFlight) return;
  choiceInFlight = true;
  if (!recordedAudio.paused || window.speechSynthesis?.speaking) stopListening({ turnOff: false });
  try {
    const state = await api("/api/dating-sim/choose", { method: "POST", body: JSON.stringify({ choice_index: choiceIndex, story_id: storyId }) });
    if (listeningMode) {
      await playStandalone(sceneChoices[choiceIndex].text, "male", "내 대사 재생 중");
    }
    render(state);
  } catch (e) {
    alert(e.message);
  } finally {
    choiceInFlight = false;
  }
}

async function restart() {
  if (!confirm("처음부터 다시 시작할까요? 지금까지의 호감도는 사라집니다.")) return;
  try {
    render(await api("/api/dating-sim/restart", { method: "POST", body: JSON.stringify({ story_id: storyId }) }));
  } catch (e) {
    alert(e.message);
  }
}

function replayCurrentView() {
  if (!$("map-view").classList.contains("hidden")) {
    return playMapOpening()
      .then(() => updateListeningControls("답장을 골라주세요"));
  }
  if (!$("result-view").classList.contains("hidden") && latestState?.choice_result) {
    return playStandalone(latestState.choice_result.line, "female", `${latestState.character_name} 대사 재생 중`)
      .then(() => updateListeningControls("다음 장면을 눌러 계속"));
  }
  if (!$("ending-view").classList.contains("hidden") && latestState?.ending) {
    return playStandalone(latestState.ending.lines.join("\n"), "female", `${latestState.character_name} 엔딩 재생 중`)
      .then(() => updateListeningControls("엔딩 음성 완료"));
  }
  if (typewriterTimer) {
    stopTypewriter();
    const line = sceneLines[sceneLineIndex];
    renderAnnotatedText($("dialogue-text"), typeof line === "string" ? line : line.text);
    onLineFullyShown();
    return Promise.resolve();
  }
  speakCurrentLine();
  return Promise.resolve();
}

$("dialogue-next").addEventListener("click", (event) => {
  event.stopPropagation();
  advanceLine();
});
document.getElementById("scene-view").addEventListener("click", (event) => {
  if (event.target.closest(".listening-controls")) return;
  if (event.target.closest(".choice-button")) return;
  if (!$("choice-list").classList.contains("hidden")) return;
  advanceLine();
});
$("listening-toggle").addEventListener("click", (event) => {
  event.stopPropagation();
  if (listeningMode) {
    stopListening();
    return;
  }
  listeningMode = true;
  updateListeningControls("대기 중");
  replayCurrentView();
});
$("listening-replay").addEventListener("click", (event) => {
  event.stopPropagation();
  stopListening({ turnOff: false });
  listeningMode = true;
  updateListeningControls("다시 재생 준비 중");
  replayCurrentView();
});
$("listening-stop").addEventListener("click", (event) => {
  event.stopPropagation();
  stopListening();
});
document.addEventListener("visibilitychange", () => {
  if (document.hidden) stopListening();
});
window.addEventListener("pagehide", () => stopListening());
$("restart-btn").addEventListener("click", restart);
$("result-next").addEventListener("click", () => {
  const nextState = { ...latestState };
  delete nextState.choice_result;
  render(nextState);
});

updateListeningControls();
loadAudioManifest().finally(loadState);
