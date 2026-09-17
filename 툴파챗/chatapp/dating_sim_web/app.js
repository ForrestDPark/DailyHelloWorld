const $ = (id) => document.getElementById(id);
const bookId = new URLSearchParams(location.search).get("book");
let storyId = bookId && /^[0-9a-f]{20}$/.test(bookId) ? `book:${bookId}` : null;
let latestState = null;
let listeningMode = false;
let speechSequence = 0;
let audioManifest = {};
const recordedAudio = new Audio();
let pendingPlaybackResolve = null;
let choiceInFlight = false;
let mapOpeningText = "";
let sceneCharacterImage = "";

// ★ 2026-09-17: "이전장면보기버튼이없는데... 아니 이전장면 대사말고" 요청 —
// 대사창 안 ◀ 뒤로가기(현재 장면 안에서만 동작)와는 별개로, 이미 끝낸
// 과거 장면 전체를 다시 볼 수 있는 백로그. 서버에 왕복하지 않고 브라우저
// localStorage에 만남(story_id)별로 저장해서 새로고침해도 남는다.
let sceneHistory = [];
const LOCATION_LABELS = {
  cafe: "카페", park: "공원", school: "학교 앞",
  first: "첫 만남 장소", walk: "산책길", quiet: "찻집",
};

function historyStorageKey() {
  return `dating-sim-history:${storyId || "default"}`;
}

function loadSceneHistory() {
  try {
    sceneHistory = JSON.parse(localStorage.getItem(historyStorageKey()) || "[]");
  } catch (e) {
    sceneHistory = [];
  }
  updateHistoryButtonVisibility();
}

function saveSceneHistory() {
  try {
    localStorage.setItem(historyStorageKey(), JSON.stringify(sceneHistory));
  } catch (e) {
    // localStorage가 꽉 찼거나 비활성화된 환경 — 백로그는 이번 방문에서만 쓰고 조용히 넘어간다.
  }
}

function updateHistoryButtonVisibility() {
  $("history-open-btn").classList.toggle("hidden", sceneHistory.length === 0);
}

function addSceneToHistory(entry) {
  sceneHistory.push(entry);
  saveSceneHistory();
  updateHistoryButtonVisibility();
}

function clearSceneHistory() {
  sceneHistory = [];
  saveSceneHistory();
  updateHistoryButtonVisibility();
}

function renderHistoryList() {
  const list = $("history-list");
  list.replaceChildren();
  if (!sceneHistory.length) {
    const empty = document.createElement("p");
    empty.className = "history-empty";
    empty.textContent = "아직 지나간 장면이 없어요.";
    list.append(empty);
    return;
  }
  for (const entry of sceneHistory) {
    const card = document.createElement("div");
    card.className = "history-entry";
    const head = document.createElement("div");
    head.className = "history-entry-head";
    const dayLabel = document.createElement("span");
    dayLabel.textContent = `DAY ${entry.day} · ${LOCATION_LABELS[entry.location] || entry.location}`;
    head.append(dayLabel);
    const linesBox = document.createElement("div");
    linesBox.className = "history-entry-lines";
    for (const line of entry.lines) {
      const p = document.createElement("p");
      renderAnnotatedText(p, typeof line === "string" ? line : line.text);
      linesBox.append(p);
    }
    card.append(head, linesBox);
    if (entry.choiceText) {
      const choiceBox = document.createElement("div");
      choiceBox.className = "history-entry-choice";
      renderAnnotatedText(choiceBox, `▶ ${entry.choiceText}`);
      card.append(choiceBox);
    }
    list.append(card);
  }
}

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
  for (const id of ["map-view", "scene-view", "result-view", "ending-view", "lobby-view", "loading-view"]) {
    $(id).classList.toggle("hidden", id !== name);
  }
  $("listening-controls").classList.toggle("hidden", name === "loading-view" || name === "lobby-view");
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

// ★ 2026-09-17: "미연시에서도 한자클릭하면 팝업뜨게해줘" 요청 — 채팅
// (static/chat.js)의 한자 클릭 팝업(훈독·음독·한국 한자음, 단어장 저장)을
// 미연시 대사·도입부·선택지·엔딩 텍스트에도 그대로 이식한다. 사전 데이터와
// 단어장 API는 채팅과 동일한 것을 그대로 재사용한다.
let kanjiDictionaryPromise = null;
let kanjiPopover = null;
let kanjiFavoritesPromise = null;
let kanjiFavorites = new Set();
const KANJI_PATTERN = /[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]/u;

function katakanaToHiragana(text) {
  return String(text || "").replace(/[ァ-ヶ]/g, (ch) => String.fromCharCode(ch.charCodeAt(0) - 0x60));
}

function loadKanjiDictionary() {
  if (!kanjiDictionaryPromise) {
    kanjiDictionaryPromise = fetch("/static/data/kanjidic-readings.json?v=20260914-hanja-v3", { cache: "no-cache" })
      .then((response) => {
        if (!response.ok) throw new Error(`KANJIDIC2 HTTP ${response.status}`);
        return response.json();
      })
      .then((data) => data.entries || {})
      .catch((error) => {
        kanjiDictionaryPromise = null;
        console.error("일본어 한자 독음 사전을 불러오지 못했습니다.", error);
        return {};
      });
  }
  return kanjiDictionaryPromise;
}

function closeKanjiPopover() {
  kanjiPopover?.remove();
  kanjiPopover = null;
}

function formatKoreanHanjaGloss(reading) {
  const meaning = String(reading.meaning || "").trim();
  const sound = String(reading.sound || "").trim();
  if (meaning === "불러오는 중…" || sound === "불러오는 중…") return "불러오는 중…";
  if (!meaning && !sound) return "해당 없음";
  if (!meaning) return sound;
  if (!sound) return meaning;
  const alreadyEndsWithSound = sound.split("·").some((item) => item && meaning.endsWith(` ${item}`));
  return alreadyEndsWithSound ? meaning : `${meaning} ${sound}`;
}

// 단어장 API는 실제 로그인 계정에서만 동작한다(로컬 소유자 무인증 우회는
// 401을 돌려받는다) — game의 api()는 401에서 홈으로 튕겨버리므로 여기서는
// 별도의 조용한 fetch를 쓴다. 실패해도 팝업 자체(훈독·음독 보기)는 그대로 쓸 수 있다.
function loadKanjiFavorites(force = false) {
  if (force) kanjiFavoritesPromise = null;
  if (!kanjiFavoritesPromise) {
    kanjiFavoritesPromise = fetch("/api/me/japanese-kanji-favorites", { credentials: "same-origin" })
      .then((response) => (response.ok ? response.json() : []))
      .then((items) => {
        kanjiFavorites = new Set(items.map((item) => item.character));
        return items;
      })
      .catch(() => []);
  }
  return kanjiFavoritesPromise;
}

async function toggleKanjiFavorite(character, button) {
  await loadKanjiFavorites();
  const removing = kanjiFavorites.has(character);
  button.disabled = true;
  try {
    const response = await fetch(`/api/me/japanese-kanji-favorites/${encodeURIComponent(character)}`, {
      method: removing ? "DELETE" : "PUT",
      credentials: "same-origin",
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    if (removing) kanjiFavorites.delete(character); else kanjiFavorites.add(character);
    button.classList.toggle("active", !removing);
    button.textContent = removing ? "☆ 저장" : "★ 저장됨";
    button.setAttribute("aria-label", removing ? `${character} 단어장에 저장` : `${character} 단어장에서 제거`);
  } catch (e) {
    alert("한자를 저장하지 못했습니다.");
  } finally {
    button.disabled = false;
  }
}

function showKanjiPopover(character, reading, anchor) {
  closeKanjiPopover();
  const popover = document.createElement("section");
  popover.className = "japanese-kanji-popover";
  popover.setAttribute("role", "dialog");
  popover.setAttribute("aria-label", `${character} 한자 뜻과 음`);
  const close = document.createElement("button");
  close.type = "button";
  close.className = "japanese-kanji-popover-close";
  close.textContent = "×";
  close.setAttribute("aria-label", "독음 닫기");
  close.addEventListener("click", closeKanjiPopover);
  const favorite = document.createElement("button");
  favorite.type = "button";
  favorite.className = "japanese-kanji-favorite";
  favorite.textContent = "☆ 저장";
  favorite.setAttribute("aria-label", `${character} 단어장에 저장`);
  loadKanjiFavorites().then(() => {
    if (!favorite.isConnected) return;
    const active = kanjiFavorites.has(character);
    favorite.classList.toggle("active", active);
    favorite.textContent = active ? "★ 저장됨" : "☆ 저장";
    favorite.setAttribute("aria-label", active ? `${character} 단어장에서 제거` : `${character} 단어장에 저장`);
  });
  favorite.addEventListener("click", () => toggleKanjiFavorite(character, favorite));
  const glyph = document.createElement("strong");
  glyph.className = "japanese-kanji-popover-glyph";
  glyph.lang = "ja";
  glyph.textContent = character;
  const readings = document.createElement("div");
  readings.className = "japanese-kanji-popover-readings";
  const rows = [
    ["뜻·음", formatKoreanHanjaGloss(reading)],
    ["훈독", (reading.kun || []).join("・") || "해당 없음"],
    ["음독", (reading.on || []).map(katakanaToHiragana).join("・") || "해당 없음"],
  ];
  for (const [label, displayValue] of rows) {
    const row = document.createElement("div");
    const heading = document.createElement("span");
    heading.textContent = label;
    const value = document.createElement("b");
    value.lang = "ja";
    value.textContent = displayValue;
    row.append(heading, value);
    readings.appendChild(row);
  }
  popover.append(close, favorite, glyph, readings);
  document.body.appendChild(popover);
  kanjiPopover = popover;
  const rect = anchor.getBoundingClientRect();
  const width = popover.offsetWidth;
  popover.style.left = `${Math.max(12, Math.min(rect.left + rect.width / 2 - width / 2, innerWidth - width - 12))}px`;
  const desiredTop = rect.bottom + 10;
  popover.style.top = `${Math.max(12, Math.min(desiredTop, innerHeight - popover.offsetHeight - 12))}px`;
}

function decorateKanji(container) {
  const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT, {
    acceptNode(node) {
      if (!KANJI_PATTERN.test(node.nodeValue || "")) return NodeFilter.FILTER_REJECT;
      if (node.parentElement?.closest("rt")) return NodeFilter.FILTER_REJECT;
      return NodeFilter.FILTER_ACCEPT;
    },
  });
  const nodes = [];
  while (walker.nextNode()) nodes.push(walker.currentNode);
  for (const node of nodes) {
    const fragment = document.createDocumentFragment();
    for (const part of Array.from(node.nodeValue || "")) {
      if (!KANJI_PATTERN.test(part)) {
        fragment.appendChild(document.createTextNode(part));
        continue;
      }
      const button = document.createElement("button");
      button.type = "button";
      button.className = "japanese-kanji-char";
      button.lang = "ja";
      button.textContent = part;
      button.setAttribute("aria-label", `${part} 한자 뜻과 음 보기`);
      button.addEventListener("click", async (event) => {
        event.stopPropagation();
        showKanjiPopover(part, { sound: "불러오는 중…", meaning: "불러오는 중…", on: [], kun: [] }, button);
        const dictionary = await loadKanjiDictionary();
        if (!button.isConnected) return;
        const reading = dictionary[part] || { sound: "", meaning: "", on: [], kun: [] };
        showKanjiPopover(part, reading, button);
      });
      fragment.appendChild(button);
    }
    node.replaceWith(fragment);
  }
}

document.addEventListener("click", (event) => {
  if (kanjiPopover && !kanjiPopover.contains(event.target) && !event.target.closest(".japanese-kanji-char")) {
    closeKanjiPopover();
  }
});

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
  decorateKanji(element);
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
  $("dialogue-back").classList.toggle("hidden", sceneLineIndex === 0);
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

// ★ 2026-09-17: "이전대사로 다시넘어갈수있게해줘" 요청 — 다음 줄로만
// 넘어가던 대사창에 이전 줄로 돌아가는 버튼을 추가한다. 선택지가 떠 있는
// 마지막 줄에서 뒤로 가면 선택지는 다시 숨기고(typeLine이 처리) 그 앞
// 줄부터 다시 읽을 수 있다.
function goToPreviousLine() {
  if (sceneLineIndex === 0) return;
  if (!recordedAudio.paused || window.speechSynthesis?.speaking) stopListening({ turnOff: false });
  sceneLineIndex -= 1;
  typeLine(sceneLines[sceneLineIndex]);
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
  loadSceneHistory();
  showView("loading-view");
  try {
    render(await api(`/api/dating-sim/state${storyQuery()}`));
  } catch (e) {
    $("loading-view").querySelector("p").textContent = e.message;
  }
}

// ★ 2026-09-17: "만남마다 나가기하면 그 진행상태가 세이브되서 다시 미연시
// 누르면 이전 진행 이어가기, 새로운 만남 중에 선택해서 플레이할수있으면
// 좋겠어" → 이어서 "모든 목록이 다 나오는 것 같은데 그렇게 하지 말고
// 이어하기랑 새 만남 하기 이거 두 개만 목록이 떠서 선택하게끔" 요청 —
// 저장된 만남이 여러 개여도 전부 나열하지 않고, 가장 최근에 하던 만남
// 하나로 이어가는 "이어하기"와 "새로운 만남 시작하기" 두 버튼만 보여준다.
// book= 딥링크(일본어 선생님 채팅 링크)로 들어온 경우는 그대로 그 작품으로
// 바로 들어간다. 저장된 만남이 하나도 없으면(이전에 했던 작품이 없으면)
// 로비 없이 곧바로 새로 시작한다.
function lobbyStatusText(encounter) {
  return encounter.completed
    ? `엔딩 · ${encounter.ending_title}`
    : `DAY ${encounter.day} / ${encounter.total_days} · 호감도 ${encounter.affection}`;
}

function renderLobby(mostRecentEncounter) {
  const continueBtn = $("lobby-continue-btn");
  continueBtn.replaceChildren();
  continueBtn.classList.remove("hidden");
  if (mostRecentEncounter.character_image) {
    const img = document.createElement("img");
    img.src = mostRecentEncounter.character_image;
    img.alt = mostRecentEncounter.character_name;
    continueBtn.append(img);
  }
  const info = document.createElement("div");
  info.className = "lobby-card-info";
  const title = document.createElement("strong");
  title.textContent = "이어하기";
  const subtitle = document.createElement("span");
  subtitle.textContent = mostRecentEncounter.source_title
    ? `${mostRecentEncounter.character_name} · ${mostRecentEncounter.source_title}`
    : mostRecentEncounter.character_name;
  const status = document.createElement("span");
  status.textContent = lobbyStatusText(mostRecentEncounter);
  info.append(title, subtitle, status);
  continueBtn.append(info);
  continueBtn.onclick = () => enterStory(mostRecentEncounter.story_id);
  showView("lobby-view");
}

function enterStory(nextStoryId) {
  storyId = nextStoryId;
  loadState();
}

async function boot() {
  if (storyId) return loadState();
  showView("loading-view");
  try {
    const encounters = await api("/api/dating-sim/encounters");
    if (!encounters.length) return loadState();
    renderLobby(encounters[0]);
  } catch (e) {
    $("loading-view").querySelector("p").textContent = e.message;
  }
}

$("lobby-new-btn").addEventListener("click", async () => {
  showView("loading-view");
  try {
    const { story_id } = await api("/api/dating-sim/new", { method: "POST" });
    enterStory(story_id);
  } catch (e) {
    alert(e.message);
    boot();
  }
});

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
  // render(state)가 sceneLines/latestState를 다음 장면 것으로 덮어쓰기 전에,
  // 지금 끝나는 장면을 백로그용으로 미리 떼어둔다.
  const finishedEntry = {
    day: latestState?.day, location: $("stage").dataset.location,
    lines: sceneLines.slice(), choiceText: sceneChoices[choiceIndex]?.text || "",
  };
  try {
    const state = await api("/api/dating-sim/choose", { method: "POST", body: JSON.stringify({ choice_index: choiceIndex, story_id: storyId }) });
    if (listeningMode) {
      await playStandalone(sceneChoices[choiceIndex].text, "male", "내 대사 재생 중");
    }
    addSceneToHistory(finishedEntry);
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
    clearSceneHistory();
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
$("dialogue-back").addEventListener("click", (event) => {
  event.stopPropagation();
  goToPreviousLine();
});
document.getElementById("scene-view").addEventListener("click", (event) => {
  if (event.target.closest(".listening-controls")) return;
  if (event.target.closest(".choice-button")) return;
  if (event.target.closest("#dialogue-back")) return;
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

// ★ 2026-09-17: "호감도 나오고 다음장면으로를 클릭하는게아니라 터치하면
// 바로 다음장면으로 넘어가" 요청 — 버튼을 정확히 눌러야만 넘어가던 것을,
// 화면 아무 곳이나 터치해도 넘어가도록 scene-view와 같은 패턴을 적용한다.
function advancePastResult() {
  const nextState = { ...latestState };
  delete nextState.choice_result;
  render(nextState);
}
$("result-next").addEventListener("click", (event) => {
  event.stopPropagation();
  advancePastResult();
});
document.getElementById("result-view").addEventListener("click", (event) => {
  if (event.target.closest(".listening-controls")) return;
  advancePastResult();
});

$("history-open-btn").addEventListener("click", () => {
  renderHistoryList();
  $("history-overlay").classList.remove("hidden");
});
$("history-close-btn").addEventListener("click", () => {
  $("history-overlay").classList.add("hidden");
});
$("history-overlay").addEventListener("click", (event) => {
  if (event.target === $("history-overlay")) $("history-overlay").classList.add("hidden");
});

updateListeningControls();
loadAudioManifest().finally(boot);
