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
    dayLabel.textContent = `지난 장면 · ${LOCATION_LABELS[entry.location] || entry.location}`;
    head.append(dayLabel);
    const linesBox = document.createElement("div");
    linesBox.className = "history-entry-lines";
    for (const line of entry.lines) {
      const p = document.createElement("p");
      renderAnnotatedText(p, typeof line === "string" ? line : line.text, entry.vocab || null);
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
  const progress = Math.max(0, Math.min(100, Math.round(((state.day - 1) / state.total_days) * 100)));
  $("hud-day").textContent = `이야기 진행 ${progress}%`;
  $("affection-value").textContent = state.affection;
  $("affection-value").parentElement.setAttribute("aria-label", `호감도 ${state.affection}점`);
  $("affection-bar").style.width = `${Math.max(0, Math.min(100, state.affection))}%`;
  // 관리자 계정에서만 시나리오 트리 버튼을 보여준다(서버도 소유자만 허용).
  $("tree-open-btn").classList.toggle("hidden", !state.is_admin);
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
// ★ 2026-09-18: "쓰여진 그 단어는 대사에서 글자색상을 다르게... 단어클릭도
// 가능하고 클릭시에 팝업이 떠서 훈음과 한국어뜻을 보고 단어장 즐겨찾기도
// 되면 좋겠어" 요청 — 이번 장면에 든 학습 단어 목록({ja,reading,ko} 배열)을
// 담아둔다. renderAnnotatedText가 이 목록과 일치하는 [한자|읽기] 태그를
// 만나면 개별 한자 클릭 대신 단어 전체 클릭(단어 팝업)으로 바꾼다. ★
// 2026-09-19: AI 생성 시나리오는 한 장면에 여러 단어가 들어가 배열로 관리.
let sceneVocab = [];

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

// \u2605 2026-09-18: "\ub2e8\uc5b4\ud074\ub9ad\ub3c4 \uac00\ub2a5\ud558\uace0 \ud074\ub9ad\uc2dc\uc5d0 \ud31d\uc5c5\uc774 \ub5a0\uc11c \ud6c8\uc74c\uacfc
// \ud55c\uad6d\uc5b4\ub73b\uc744 \ubcf4\uace0 \ub2e8\uc5b4\uc7a5 \uc990\uaca8\ucc3e\uae30\ub3c4 \ub418\uba74 \uc88b\uaca0\uc5b4" \uc694\uccad \u2014 \ud45c\ud604 \uc0bd\uc785
// \ub2e8\uc5b4(sceneVocab)\ub294 \ud55c\uc790 1\uae00\uc790\uac00 \uc544\ub2c8\ub77c \ub2e8\uc5b4 \uc804\uccb4(\uc608: "\u6211\u6162")\ub77c\uc11c
// japanese_kanji_favorites(1\uae00\uc790 \uc804\uc6a9) \ud14c\uc774\ube14\uc744 \ubabb \uc4f4\ub2e4. \uc774\ubbf8 \uc788\ub294 \ubc94\uc6a9
// vocabulary_entries \ud14c\uc774\ube14(/api/me/vocabulary, language="japanese"\uae4c\uc9c0
// API \ub808\ubca8\uc5d0\uc120 \uc774\ubbf8 \uc9c0\uc6d0)\uc744 \uadf8\ub300\ub85c \uc7ac\uc0ac\uc6a9\ud55c\ub2e4 \u2014 \uc0c8 \ud14c\uc774\ube14\u00b7\uc5d4\ub4dc\ud3ec\uc778\ud2b8 \ubd88\ud544\uc694.
let vocabPopover = null;
let vocabFavoritesPromise = null;
let vocabFavorites = new Map(); // term(ja) -> entry id

function loadVocabFavorites(force = false) {
  if (force) vocabFavoritesPromise = null;
  if (!vocabFavoritesPromise) {
    vocabFavoritesPromise = fetch("/api/me/vocabulary?language=japanese", { credentials: "same-origin" })
      .then((response) => (response.ok ? response.json() : []))
      .then((items) => {
        vocabFavorites = new Map(items.map((item) => [item.term, item.id]));
        return items;
      })
      .catch(() => []);
  }
  return vocabFavoritesPromise;
}

async function toggleVocabFavorite(word, button) {
  await loadVocabFavorites();
  const removing = vocabFavorites.has(word.ja);
  button.disabled = true;
  try {
    if (removing) {
      const entryId = vocabFavorites.get(word.ja);
      const response = await fetch(`/api/me/vocabulary/${entryId}`, { method: "DELETE", credentials: "same-origin" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      vocabFavorites.delete(word.ja);
    } else {
      const response = await fetch("/api/me/vocabulary", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ language: "japanese", term: word.ja, meaning: word.ko, pronunciation: word.reading }),
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const saved = await response.json();
      vocabFavorites.set(word.ja, saved.id);
    }
    button.classList.toggle("active", !removing);
    button.textContent = removing ? "\u2606 \uc800\uc7a5" : "\u2605 \uc800\uc7a5\ub428";
    button.setAttribute("aria-label", removing ? `${word.ja} \ub2e8\uc5b4\uc7a5\uc5d0 \uc800\uc7a5` : `${word.ja} \ub2e8\uc5b4\uc7a5\uc5d0\uc11c \uc81c\uac70`);
  } catch (e) {
    alert("\ub2e8\uc5b4\ub97c \uc800\uc7a5\ud558\uc9c0 \ubabb\ud588\uc2b5\ub2c8\ub2e4.");
  } finally {
    button.disabled = false;
  }
}

function closeVocabPopover() {
  vocabPopover?.remove();
  vocabPopover = null;
}

function showVocabWordPopover(word, anchor) {
  closeKanjiPopover();
  closeVocabPopover();
  const popover = document.createElement("section");
  popover.className = "japanese-kanji-popover";
  popover.setAttribute("role", "dialog");
  popover.setAttribute("aria-label", `${word.ja} \ub2e8\uc5b4 \ub73b\uacfc \uc77d\uae30`);
  const close = document.createElement("button");
  close.type = "button";
  close.className = "japanese-kanji-popover-close";
  close.textContent = "\u00d7";
  close.setAttribute("aria-label", "\ub2e8\uc5b4 \ub73b \ub2eb\uae30");
  close.addEventListener("click", closeVocabPopover);
  const favorite = document.createElement("button");
  favorite.type = "button";
  favorite.className = "japanese-kanji-favorite";
  favorite.textContent = "\u2606 \uc800\uc7a5";
  favorite.setAttribute("aria-label", `${word.ja} \ub2e8\uc5b4\uc7a5\uc5d0 \uc800\uc7a5`);
  loadVocabFavorites().then(() => {
    if (!favorite.isConnected) return;
    const active = vocabFavorites.has(word.ja);
    favorite.classList.toggle("active", active);
    favorite.textContent = active ? "\u2605 \uc800\uc7a5\ub428" : "\u2606 \uc800\uc7a5";
    favorite.setAttribute("aria-label", active ? `${word.ja} \ub2e8\uc5b4\uc7a5\uc5d0\uc11c \uc81c\uac70` : `${word.ja} \ub2e8\uc5b4\uc7a5\uc5d0 \uc800\uc7a5`);
  });
  favorite.addEventListener("click", () => toggleVocabFavorite(word, favorite));
  const glyph = document.createElement("strong");
  glyph.className = "japanese-kanji-popover-glyph";
  glyph.lang = "ja";
  glyph.textContent = word.ja;
  const readings = document.createElement("div");
  readings.className = "japanese-kanji-popover-readings";
  const rows = [
    ["\ud6c8\uc74c", word.reading || "\ud574\ub2f9 \uc5c6\uc74c"],
    ["\ub73b", word.ko || "\ud574\ub2f9 \uc5c6\uc74c"],
  ];
  for (const [label, displayValue] of rows) {
    const row = document.createElement("div");
    const heading = document.createElement("span");
    heading.textContent = label;
    const value = document.createElement("b");
    value.lang = label === "\ud6c8\uc74c" ? "ja" : "ko";
    value.textContent = displayValue;
    row.append(heading, value);
    readings.appendChild(row);
  }
  popover.append(close, favorite, glyph, readings);
  document.body.appendChild(popover);
  vocabPopover = popover;
  const rect = anchor.getBoundingClientRect();
  const width = popover.offsetWidth;
  popover.style.left = `${Math.max(12, Math.min(rect.left + rect.width / 2 - width / 2, innerWidth - width - 12))}px`;
  const desiredTop = rect.bottom + 10;
  popover.style.top = `${Math.max(12, Math.min(desiredTop, innerHeight - popover.offsetHeight - 12))}px`;
}

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
  closeVocabPopover();
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
      // 표현 삽입 단어(vocab-word)는 한자 낱글자 클릭이 아니라 단어 전체
      // 클릭(단어 팝업)으로 처리하므로, 개별 한자 버튼으로 다시 쪼개지 않는다.
      if (node.parentElement?.closest("[data-vocab-word]")) return NodeFilter.FILTER_REJECT;
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
  if (vocabPopover && !vocabPopover.contains(event.target) && !event.target.closest(".vocab-word")) {
    closeVocabPopover();
  }
});

// vocabWords: 학습 단어 하나(객체) 또는 여러 개(배열). ★ 2026-09-19: AI 생성
// 시나리오는 한 장면에 여러 단어가 들어가므로 배열을 받아 태그별로 매칭한다.
function renderAnnotatedText(element, text, vocabWords = null) {
  element.replaceChildren();
  const list = Array.isArray(vocabWords) ? vocabWords : (vocabWords ? [vocabWords] : []);
  const wordByTag = new Map(list.map((w) => [`${w.ja}|${w.reading}`, w]));
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
      // 학습 단어와 일치하는 태그만 색상을 다르게 하고 단어 전체 클릭(단어
      // 팝업)을 붙인다 — 같은 줄의 다른 한자는 그대로 decorateKanji의 낱글자
      // 클릭을 쓴다.
      const word = wordByTag.get(`${match[1]}|${match[2]}`);
      if (word) {
        ruby.classList.add("vocab-word");
        ruby.dataset.vocabWord = "1";
        ruby.tabIndex = 0;
        ruby.setAttribute("role", "button");
        ruby.setAttribute("aria-label", `${word.ja} 단어 뜻 보기`);
        ruby.addEventListener("click", (event) => {
          event.stopPropagation();
          showVocabWordPopover(word, ruby);
        });
      }
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
  const speakerName = $("speaker-name");
  if (narrator) speakerName.textContent = "主人公 · 나";
  else renderAnnotatedText(speakerName, latestState?.character_name || "");
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
      renderAnnotatedText(el, text, sceneVocab);
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
    renderAnnotatedText($("dialogue-text"), typeof line === "string" ? line : line.text, sceneVocab);
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
  sceneVocab = state.scene.vocab_words || (state.scene.vocab ? [state.scene.vocab] : []);
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
  renderAnnotatedText($("result-speaker-name"), state.character_name);
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
  renderAnnotatedText($("ending-speaker-name"), state.character_name);
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
  const progress = Math.max(0, Math.min(100, Math.round(((encounter.day - 1) / encounter.total_days) * 100)));
  return encounter.completed
    ? `엔딩 · ${encounter.ending_title}`
    : `이야기 진행 ${progress}% · 호감도 ${encounter.affection}`;
}

function renderLobby(mostRecentEncounter) {
  const continueBtn = $("lobby-continue-btn");
  continueBtn.replaceChildren();
  continueBtn.classList.remove("hidden");
  if (mostRecentEncounter.character_image) {
    const img = document.createElement("img");
    img.src = mostRecentEncounter.character_image;
    img.alt = plainText(mostRecentEncounter.character_name);
    continueBtn.append(img);
  }
  const info = document.createElement("div");
  info.className = "lobby-card-info";
  const title = document.createElement("strong");
  title.textContent = "이어하기";
  // ★ 2026-09-17: "작품명은 안나오면좋겠어 그냥 여자이름이랑 현재까지의
  // 만남요약정도만 나오면 좋겠어" 요청 — source_title(EPUB 제목)은 화면에
  // 절대 노출하지 않는다. 이름 + 진행 요약만 보여준다.
  const subtitle = document.createElement("span");
  renderAnnotatedText(subtitle, mostRecentEncounter.character_name);
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
    vocab: sceneVocab,
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
    renderAnnotatedText($("dialogue-text"), typeof line === "string" ? line : line.text, sceneVocab);
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

// ★ 2026-09-18: "미연시스템 관리자 모드에서는 시나리오트리를 볼수있게...
// 학습카드에서 나온 표현들이 어떻게 시나리오상에 작용되었는지 확인" 요청 —
// 관리자(state.is_admin)에게만 뜨는 버튼으로 지금 이야기의 전체 구조를
// 조회한다(진행 상태는 안 건드림). 각 요일마다 삽입된 EPUB 학습 단어와
// 그 단어가 실제로 쓰인 대사 줄을 강조해 보여준다.
function treeLineDom(line) {
  const p = document.createElement("p");
  p.className = "tree-line";
  p.classList.toggle("tree-line-narrator", line.speaker === "narrator");
  p.classList.toggle("tree-line-vocab", !!line.is_vocab);
  p.classList.toggle("tree-line-outro", !!line.is_outro);
  const text = document.createElement("span");
  renderAnnotatedText(text, line.text);
  p.append(text);
  if (line.is_outro) {
    const tag = document.createElement("span");
    tag.className = "tree-tag";
    tag.textContent = "선택지가 답하는 줄";
    p.append(tag);
  }
  return p;
}

// ★ 2026-09-19: "학습카드와 대사전반을 읽고 어떤 대사를 활용하고 어떤
// 단어를 시나리오에서 활용했는지 간단한 보고서... 항목화해서 테이블로"
// 요청 — 시나리오 트리 맨 위에 보고서 테이블을 붙인다.
function makeTreeTable(headers, rows) {
  const table = document.createElement("table");
  table.className = "tree-table";
  const thead = document.createElement("thead");
  const htr = document.createElement("tr");
  for (const h of headers) {
    const th = document.createElement("th");
    th.textContent = h;
    htr.append(th);
  }
  thead.append(htr);
  table.append(thead);
  const tbody = document.createElement("tbody");
  for (const row of rows) {
    const tr = document.createElement("tr");
    for (const cell of row) {
      const td = document.createElement("td");
      if (cell instanceof Node) td.append(cell);
      else td.textContent = cell == null ? "" : String(cell);
      tr.append(td);
    }
    tbody.append(tr);
  }
  table.append(tbody);
  return table;
}

const VOCAB_CATEGORY_LABELS = {
  household: "집안일", help: "도움", worry: "고민", preference: "취향",
  memory: "추억", plan: "계획", feeling: "감정", outcome: "결과", general: "일반",
};

function renderScenarioReport(body, tree) {
  const report = tree.report;
  const head = document.createElement("div");
  head.className = "tree-section-head";
  head.textContent = "📊 작품·시나리오 보고서";
  body.append(head);

  // 규모 요약 칩
  const c = report.corpus;
  const summary = document.createElement("div");
  summary.className = "tree-report-summary";
  const chips = [
    `원작 대사 ${c.transcript_lines}줄 · ${c.transcript_scenes}장면`,
    `학습카드 ${c.study_card_scenes}장면`,
    `학습 단어 ${report.vocabulary_pool_count}개`,
    `핵심 표현 ${c.expressions_total}개`,
    `시나리오 활용 단어 ${report.vocabulary_used_count}개`,
    `시나리오 활용 표현 ${report.expression_used_count || 0}개`,
  ];
  for (const text of chips) {
    const chip = document.createElement("span");
    chip.className = "tree-report-chip";
    chip.textContent = text;
    summary.append(chip);
  }
  body.append(summary);

  const note = document.createElement("p");
  note.className = "tree-report-note";
  note.textContent = "시나리오는 원작 대사를 그대로 옮기지 않습니다. 학습카드에서 뽑은 단어만 매일 하나씩 상황 속에 녹여 씁니다(아래 표의 초록 줄).";
  body.append(note);

  // 표 1 — 요일별 시나리오 구성
  const t1head = document.createElement("div");
  t1head.className = "tree-table-title";
  t1head.textContent = "요일별 시나리오 구성";
  body.append(t1head);
  const dayRows = report.scenario_breakdown.map((d) => {
    let wordCell = "—";
    if (d.vocab) {
      const w = document.createElement("span");
      w.lang = "ja";
      w.className = "tree-table-word";
      w.textContent = `${d.vocab.ja}(${d.vocab.reading}) ${d.vocab.ko}`;
      wordCell = w;
    }
    const cat = d.vocab_category ? (VOCAB_CATEGORY_LABELS[d.vocab_category] || d.vocab_category) : "—";
    const places = d.locations.map((l) => l.label).join(" / ");
    return [`D${d.day}`, d.topic, wordCell, cat, places];
  });
  body.append(makeTreeTable(["일차", "대화 주제", "삽입 단어", "분류", "장소 선택지"], dayRows));

  // 표 2 — 학습 단어 활용 현황 (활용된 것 먼저, 나머지는 접기)
  const used = report.vocabulary_usage.filter((w) => w.used_days.length);
  const unused = report.vocabulary_usage.filter((w) => !w.used_days.length);
  if (used.length) {
    const t2head = document.createElement("div");
    t2head.className = "tree-table-title";
    t2head.textContent = `시나리오에 쓰인 학습 단어 (${used.length}개)`;
    body.append(t2head);
    const usedRows = used.map((w) => {
      const word = document.createElement("span");
      word.lang = "ja";
      word.className = "tree-table-word";
      word.textContent = `${w.ja}(${w.reading})`;
      return [word, w.ko, VOCAB_CATEGORY_LABELS[w.category] || w.category, w.used_days.map((d) => `D${d}`).join(", ")];
    });
    body.append(makeTreeTable(["단어", "뜻", "분류", "활용 요일"], usedRows));
  }
  if (unused.length) {
    const details = document.createElement("details");
    details.className = "tree-unused";
    const summaryEl = document.createElement("summary");
    summaryEl.textContent = `시나리오에 아직 안 쓰인 학습 단어 ${unused.length}개 (탭해서 펼치기)`;
    details.append(summaryEl);
    const unusedRows = unused.map((w) => {
      const word = document.createElement("span");
      word.lang = "ja";
      word.className = "tree-table-word";
      word.textContent = `${w.ja}(${w.reading})`;
      return [word, w.ko, VOCAB_CATEGORY_LABELS[w.category] || w.category];
    });
    details.append(makeTreeTable(["단어", "뜻", "분류"], unusedRows));
    body.append(details);
  }

  const expressions = report.expression_usage || [];
  const usedExpressions = expressions.filter((entry) => entry.used_days.length);
  const unusedExpressions = expressions.filter((entry) => !entry.used_days.length);
  if (usedExpressions.length) {
    const heading = document.createElement("div");
    heading.className = "tree-table-title";
    heading.textContent = `시나리오에 쓰인 핵심 표현 (${usedExpressions.length}개)`;
    body.append(heading);
    body.append(makeTreeTable(["표현", "뜻", "활용 요일"], usedExpressions.map((entry) => [
      `${entry.ja}${entry.reading ? ` (${entry.reading})` : ""}`,
      entry.ko,
      entry.used_days.map((day) => `D${day}`).join(", "),
    ])));
  }
  if (unusedExpressions.length) {
    const details = document.createElement("details");
    details.className = "tree-unused";
    const summaryEl = document.createElement("summary");
    summaryEl.textContent = `시나리오에 아직 안 쓰인 핵심 표현 ${unusedExpressions.length}개 (탭해서 펼치기)`;
    details.append(summaryEl);
    details.append(makeTreeTable(["표현", "뜻"], unusedExpressions.map((entry) => [
      `${entry.ja}${entry.reading ? ` (${entry.reading})` : ""}`,
      entry.ko,
    ])));
    body.append(details);
  }
}

function renderScenarioTree(tree) {
  const body = $("tree-body");
  body.replaceChildren();

  const head = document.createElement("div");
  head.className = "tree-work-head";
  const workTitle = document.createElement("strong");
  renderAnnotatedText(workTitle, tree.source_title
    ? `${tree.character_name} · ${tree.source_title}`
    : tree.character_name);
  head.append(workTitle);
  const meta = document.createElement("span");
  meta.textContent = `${tree.total_days}개 장면 흐름 · 학습 단어 ${tree.vocab_pool.length}개`;
  head.append(meta);
  body.append(head);

  if (tree.report) renderScenarioReport(body, tree);

  const tocHead = document.createElement("div");
  tocHead.className = "tree-section-head";
  tocHead.textContent = "🌳 사건 흐름별 시나리오 트리";
  body.append(tocHead);

  for (const day of tree.days) {
    const dayEl = document.createElement("section");
    dayEl.className = "tree-day";
    const dayHead = document.createElement("div");
    dayHead.className = "tree-day-head";
    const dayNum = document.createElement("strong");
    dayNum.textContent = `흐름 ${day.day}`;
    dayHead.append(dayNum);
    if (day.vocab) {
      const badge = document.createElement("span");
      badge.className = "tree-vocab-badge";
      badge.lang = "ja";
      badge.textContent = `삽입 단어: ${day.vocab.ja}（${day.vocab.reading}） ${day.vocab.ko}`;
      dayHead.append(badge);
    }
    dayEl.append(dayHead);

    if (day.narration) {
      const nar = document.createElement("p");
      nar.className = "tree-narration";
      renderAnnotatedText(nar, day.narration);
      dayEl.append(nar);
    }
    if (day.openings.length) {
      const openWrap = document.createElement("div");
      openWrap.className = "tree-openings";
      const label = document.createElement("span");
      label.className = "tree-openings-label";
      label.textContent = "도입 메시지 후보";
      openWrap.append(label);
      for (const opening of day.openings) {
        const o = document.createElement("p");
        o.className = "tree-opening";
        renderAnnotatedText(o, opening);
        openWrap.append(o);
      }
      dayEl.append(openWrap);
    }

    for (const loc of day.locations) {
      const locEl = document.createElement("div");
      locEl.className = "tree-loc";
      const action = document.createElement("div");
      action.className = "tree-loc-action";
      action.textContent = `${loc.emoji || "•"} ${loc.action}`;
      locEl.append(action);
      for (const line of loc.lines) locEl.append(treeLineDom(line));
      const choices = document.createElement("div");
      choices.className = "tree-choices";
      loc.choices.forEach((choice, index) => {
        const c = document.createElement("div");
        c.className = "tree-choice";
        c.classList.toggle("tree-choice-up", choice.affection > 0);
        c.classList.toggle("tree-choice-down", choice.affection <= 0);
        const branch = document.createElement("span");
        branch.className = "tree-branch";
        branch.textContent = index === 0 ? "├" : "└";
        const label = document.createElement("span");
        label.className = "tree-choice-text";
        renderAnnotatedText(label, choice.text);
        const aff = document.createElement("span");
        aff.className = "tree-aff";
        aff.textContent = `${choice.affection > 0 ? "+" : ""}${choice.affection}`;
        c.append(branch, label, aff);
        choices.append(c);
      });
      locEl.append(choices);
      dayEl.append(locEl);
    }
    body.append(dayEl);
  }

  const endings = document.createElement("section");
  endings.className = "tree-endings";
  const endHead = document.createElement("strong");
  endHead.textContent = "엔딩 분기 (누적 호감도)";
  endings.append(endHead);
  for (const ending of tree.endings) {
    const e = document.createElement("div");
    e.className = "tree-ending";
    e.textContent = `호감도 ${ending.min_affection}+ → ${ending.title}`;
    endings.append(e);
  }
  body.append(endings);
}

async function openScenarioTree() {
  $("tree-body").replaceChildren(Object.assign(document.createElement("p"), {
    className: "tree-loading", textContent: "불러오는 중...",
  }));
  $("tree-overlay").classList.remove("hidden");
  try {
    const tree = await api(`/api/dating-sim/scenario-tree${storyQuery()}`);
    renderScenarioTree(tree);
  } catch (e) {
    $("tree-body").replaceChildren(Object.assign(document.createElement("p"), {
      className: "tree-loading", textContent: e.message,
    }));
  }
}

$("tree-open-btn").addEventListener("click", openScenarioTree);
$("tree-close-btn").addEventListener("click", () => {
  $("tree-overlay").classList.add("hidden");
});
$("tree-overlay").addEventListener("click", (event) => {
  if (event.target === $("tree-overlay")) $("tree-overlay").classList.add("hidden");
});

updateListeningControls();
loadAudioManifest().finally(boot);
