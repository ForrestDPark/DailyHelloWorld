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
let sceneLearningMarked = false;

// ★ 2026-09-17: "이전장면보기버튼이없는데... 아니 이전장면 대사말고" 요청 —
// 대사창 안 ◀ 뒤로가기(현재 장면 안에서만 동작)와는 별개로, 이미 끝낸
// 과거 장면 전체를 다시 볼 수 있는 백로그. 서버에 왕복하지 않고 브라우저
// localStorage에 만남(story_id)별로 저장해서 새로고침해도 남는다.
let sceneHistory = [];
const LOCATION_LABELS = {
  cafe: "카페", park: "공원", school: "학교 앞",
  first: "첫 만남 장소", walk: "산책길", quiet: "찻집",
};

function setSafeImage(element, source, fallback="/dating-sim/static/reina.png") {
  element.onerror = () => {
    element.onerror = null;
    element.src = fallback;
  };
  element.src = source || fallback;
  // ★ 2026-09-23: "사진클릭하면 사진확대되게해줘" 요청 — 초상화를 누르면
  // 잘리지 않은 원본 비율 그대로 크게 볼 수 있게 한다.
  element.classList.add("zoomable-portrait");
  // scene-view 전체에 "탭하면 다음 대사로 넘어가기" 핸들러가 걸려 있어서
  // (아래 document.getElementById("scene-view") 리스너), 초상화를 눌렀을
  // 때 확대와 대사 넘기기가 동시에 일어나지 않도록 이벤트 버블링을 막는다.
  element.onclick = (event) => {
    event.stopPropagation();
    openImageLightbox(element.src, element.alt);
  };
}

function closeImageLightbox() {
  document.querySelector(".image-lightbox-overlay")?.remove();
}

function openImageLightbox(src, alt) {
  if (!src) return;
  closeImageLightbox();
  const overlay = document.createElement("div");
  overlay.className = "image-lightbox-overlay";
  overlay.setAttribute("role", "dialog");
  overlay.setAttribute("aria-modal", "true");
  overlay.setAttribute("aria-label", alt || "이미지 확대 보기");
  const img = document.createElement("img");
  img.src = src;
  img.alt = alt || "";
  const close = document.createElement("button");
  close.type = "button";
  close.className = "image-lightbox-close";
  close.textContent = "×";
  close.setAttribute("aria-label", "이미지 닫기");
  close.addEventListener("click", closeImageLightbox);
  overlay.append(img, close);
  overlay.addEventListener("click", (event) => {
    if (event.target === overlay) closeImageLightbox();
  });
  document.body.append(overlay);
}

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

function storyQuery(extra = {}) {
  const params = new URLSearchParams(extra);
  if (storyId) params.set("story_id", storyId);
  const qs = params.toString();
  return qs ? `?${qs}` : "";
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

// ★ 2026-09-23: "한국말로번역한 뜻으로 다바꿔줘" 요청 — 단어 하나의 번역을
// 매번 새로 조회하지 않도록 세션 안에서만 가볍게 캐시한다(서버 쪽에도
// 영구 캐시가 따로 있음).
const vocabMeaningCache = new Map();
async function fetchVocabWordMeaning(word) {
  if (vocabMeaningCache.has(word)) return vocabMeaningCache.get(word);
  try {
    const data = await api(`/api/dating-sim/vocab-meaning?word=${encodeURIComponent(word)}`);
    vocabMeaningCache.set(word, data.meaning || "");
    return data.meaning || "";
  } catch (e) {
    return "";
  }
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
  const learning = state.learning_progress;
  const progress = learning ? learning.percent : 0;
  $("hud-day").textContent = learning?.total
    ? `학습 ${learning.seen}/${learning.total} · ${progress}%`
    : `학습 진행 ${progress}%`;
  $("affection-value").textContent = state.affection;
  $("affection-value").parentElement.setAttribute("aria-label", `호감도 ${state.affection}점`);
  $("affection-bar").style.width = `${Math.max(0, Math.min(100, state.affection))}%`;
  // 관리자 계정에서만 시나리오 트리 버튼을 보여준다(서버도 소유자만 허용).
  $("tree-open-btn").classList.toggle("hidden", !state.is_admin);
  $("story-list-btn").classList.toggle("hidden", !state.is_admin);
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
// ★ 2026-09-23: "서재에서 추출된 핵심 표현은 보라색으로" 요청 — 서재
// 학습카드(scene_study_cards.json)의 expressions가 시나리오 생성 단계에서
// scene.expressions_used로 내려온다. 문장형이라 태그 하나가 아니라 여러
// [한자|읽기] 태그+조사에 걸쳐 나타날 수 있어 renderAnnotatedText에서
// 평문(plain text) 좌표로 위치를 찾아 그룹으로 묶는다.
let sceneExpr = [];

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
        body: JSON.stringify({ language: "japanese", term: word.ja, meaning: word.ko || "", pronunciation: word.reading }),
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

function showVocabWordPopover(word, anchor, wordKind = "general") {
  closeKanjiPopover();
  closeVocabPopover();
  const popover = document.createElement("section");
  popover.className = `japanese-kanji-popover japanese-kanji-popover--${wordKind}`;
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
  const readingRow = document.createElement("div");
  const readingHeading = document.createElement("span");
  readingHeading.textContent = "\ud6c8\uc74c";
  const readingValueEl = document.createElement("b");
  readingValueEl.lang = "ja";
  readingValueEl.textContent = word.reading || "\ud574\ub2f9 \uc5c6\uc74c";
  readingRow.append(readingHeading, readingValueEl);
  readings.appendChild(readingRow);
  const meaningRow = document.createElement("div");
  const meaningHeading = document.createElement("span");
  meaningHeading.textContent = "\ub73b";
  const meaningValueEl = document.createElement("b");
  meaningValueEl.lang = "ko";
  meaningValueEl.textContent = word.ko || "\ubd88\ub7ec\uc624\ub294 \uc911\u2026";
  meaningRow.append(meaningHeading, meaningValueEl);
  readings.appendChild(meaningRow);
  // ★ 2026-09-23: "이렇게 한자 뜻 따로짜로가아니라 한국말로번역한 뜻으로
  // 다바꿔줘" 요청 — AI가 단어 뜻을 직접 준 sceneVocab 항목이 아니면
  // (word.ko 없음) 한자 낱글자 뜻을 "絵(그림 회) · 柄(자루 병)"처럼
  // 짜깁기해 보여줬는데, 합성어 전체의 실제 뜻이 아니라 어색했다. 서버의
  // 단어 전체 번역 API로 바꾼다.
  if (!word.ko) {
    fetchVocabWordMeaning(word.ja).then((meaning) => {
      if (!meaningValueEl.isConnected) return;
      meaningValueEl.textContent = meaning || "뜻을 찾지 못했습니다";
    });
  }
  popover.append(close, favorite, glyph, readings);
  // ★ 2026-09-23: "그 팝오버 안에서 한자 하나하나의 클릭으로 이어갈 수
  // 있게" 요청 — 단어를 이루는 한자 각각을 다시 누르면(기존 낱글자 팝업과
  // 완전히 같은 showKanjiPopover) 뜻·훈독·음독을 이어서 볼 수 있다.
  const chars = Array.from(word.ja).filter((ch) => KANJI_PATTERN.test(ch));
  if (chars.length > 1) {
    const charsSection = document.createElement("div");
    charsSection.className = "japanese-kanji-popover-word-chars";
    const label = document.createElement("span");
    label.textContent = "글자별 보기";
    const charList = document.createElement("div");
    charList.className = "japanese-kanji-popover-word-chars-list";
    for (const ch of chars) {
      const charButton = document.createElement("button");
      charButton.type = "button";
      charButton.className = "japanese-kanji-char";
      charButton.lang = "ja";
      charButton.textContent = ch;
      charButton.setAttribute("aria-label", `${ch} 한자 뜻과 음 보기`);
      charButton.addEventListener("click", async (event) => {
        event.stopPropagation();
        // charButton은 이 팝업(vocabPopover) 안에 있어서 showKanjiPopover가
        // 팝업을 닫는 순간 DOM에서 같이 제거된다 — 위치 계산용 사각형을
        // 미리 붙잡아 두는 가짜 anchor로 넘긴다.
        const rect = charButton.getBoundingClientRect();
        const anchorProxy = { getBoundingClientRect: () => rect };
        showKanjiPopover(ch, { sound: "불러오는 중…", meaning: "불러오는 중…", on: [], kun: [] }, anchorProxy);
        const dictionary = await loadKanjiDictionary();
        showKanjiPopover(ch, dictionary[ch] || { sound: "", meaning: "", on: [], kun: [] }, anchorProxy);
      });
      charList.append(charButton);
    }
    charsSection.append(label, charList);
    popover.append(charsSection);
  }
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
const ANNOTATION_PATTERN = /\[([^\]|]+)\|([^\]]+)\]|\n/g;

// text를 [한자|읽기] 태그·일반 텍스트·줄바꿈 단위("unit")로 쪼개고, 각 단위가
// 후리가나·조사를 뺀 "평문" 기준으로 어느 글자 구간([plainStart,plainEnd))에
// 해당하는지 같이 기록한다. 핵심 표현(expressions_used)은 문장형이라 태그
// 하나에 안 담기고 여러 태그+조사에 걸치므로, 평문 좌표로 위치를 찾아야
// 어디서부터 어디까지 하나의 표현인지 알 수 있다.
function splitAnnotatedUnits(text) {
  const units = [];
  let cursor = 0;
  let plainCursor = 0;
  for (const match of text.matchAll(ANNOTATION_PATTERN)) {
    if (match.index > cursor) {
      const literal = text.slice(cursor, match.index);
      units.push({ type: "text", value: literal, plainStart: plainCursor, plainEnd: plainCursor + literal.length });
      plainCursor += literal.length;
    }
    if (match[0] === "\n") {
      units.push({ type: "br" });
    } else {
      units.push({
        type: "tag", kanji: match[1], reading: match[2],
        plainStart: plainCursor, plainEnd: plainCursor + match[1].length,
      });
      plainCursor += match[1].length;
    }
    cursor = match.index + match[0].length;
  }
  if (cursor < text.length) {
    const literal = text.slice(cursor);
    units.push({ type: "text", value: literal, plainStart: plainCursor, plainEnd: plainCursor + literal.length });
  }
  return units;
}

function buildRuby(kanji, reading) {
  const ruby = document.createElement("ruby");
  ruby.append(document.createTextNode(kanji));
  const rt = document.createElement("rt");
  rt.textContent = reading;
  ruby.append(rt);
  return ruby;
}

// wordKind: "key"(빨강·핵심단어) | "expression"(보라·핵심표현) | "general"(초록·일반단어)
function markAsWordCard(el, word, wordKind) {
  el.classList.add("vocab-word", `vocab-word--${wordKind}`);
  el.dataset.vocabWord = "1";
  el.tabIndex = 0;
  el.setAttribute("role", "button");
  el.setAttribute("aria-label", `${word.ja} 단어 뜻 보기`);
  el.addEventListener("click", (event) => {
    event.stopPropagation();
    showVocabWordPopover(word, el, wordKind);
  });
}

// vocabWords: 그 장면의 핵심 단어(REMINDERS 아님, dating-sim 학습카드 vocabulary) —
// 정확히 일치하는 태그만 빨강. expressions: 서재 학습카드의 핵심 표현(문장형) —
// 평문 부분일치로 찾아 여러 태그에 걸쳐도 하나로 묶어 보라색. 둘 다 아니지만
// 순수 한자 2글자 이상인 태그는 초록(일반단어)으로 자동 승격한다.
// ★ 2026-09-23: "일반단어는 초록, 서재 핵심 표현은 보라, 핵심단어는 빨강" 요청.
function renderAnnotatedText(element, text, vocabWords = null, expressions = null) {
  element.replaceChildren();
  const vocabList = Array.isArray(vocabWords) ? vocabWords : (vocabWords ? [vocabWords] : []);
  const wordByTag = new Map(vocabList.map((w) => [`${w.ja}|${w.reading}`, w]));
  const exprList = Array.isArray(expressions) ? expressions : (expressions ? [expressions] : []);

  const units = splitAnnotatedUnits(text);
  const plainText = units.filter((u) => u.type !== "br").map((u) => (u.type === "tag" ? u.kanji : u.value)).join("");

  // 표현 구간을 평문에서 찾는다. 서로 겹치면(예: 짧은 표현이 긴 표현 안에 포함)
  // 먼저 발견되거나 더 긴 쪽을 남기고 뒤엣것은 버린다 — 한 글자가 두 표현에
  // 동시에 속하면 어느 팝업을 열지 애매해지므로 겹침을 허용하지 않는다.
  const exprRanges = [];
  for (const expr of exprList) {
    const needle = expr?.ja;
    if (!needle) continue;
    const idx = plainText.indexOf(needle);
    if (idx === -1) continue;
    exprRanges.push({ start: idx, end: idx + needle.length, item: expr });
  }
  exprRanges.sort((a, b) => a.start - b.start || (b.end - b.start) - (a.end - a.start));
  const acceptedExprRanges = [];
  let lastEnd = -1;
  for (const range of exprRanges) {
    if (range.start >= lastEnd) {
      acceptedExprRanges.push(range);
      lastEnd = range.end;
    }
  }

  function classifyUnit(unit) {
    // 표현 범위 소속 여부를 먼저 본다 — 핵심단어(vocab_words) 태그가 우연히
    // 어떤 핵심 표현의 구간 안에 들어 있으면, 표현 하나로 안 묶고 빨강 한
    // 조각만 튀어나오는 대신 표현(보라) 그룹에 그대로 포함시킨다.
    if (unit.type === "tag" || unit.type === "text") {
      const range = acceptedExprRanges.find((r) => unit.plainStart < r.end && unit.plainEnd > r.start);
      if (range) return { kind: "expression", item: range.item, rangeKey: `${range.start}-${range.end}` };
    }
    if (unit.type === "tag") {
      const vocabWord = wordByTag.get(`${unit.kanji}|${unit.reading}`);
      if (vocabWord) return { kind: "key", item: vocabWord };
    }
    if (unit.type === "tag" && unit.kanji.length >= 2 && Array.from(unit.kanji).every((ch) => KANJI_PATTERN.test(ch))) {
      return { kind: "general", item: { ja: unit.kanji, reading: unit.reading, ko: null } };
    }
    return null;
  }

  let i = 0;
  while (i < units.length) {
    const unit = units[i];
    if (unit.type === "br") {
      element.append(document.createElement("br"));
      i += 1;
      continue;
    }
    const cls = classifyUnit(unit);
    if (!cls) {
      element.append(unit.type === "tag" ? buildRuby(unit.kanji, unit.reading) : document.createTextNode(unit.value));
      i += 1;
      continue;
    }
    if (cls.kind === "key" || cls.kind === "general") {
      // vocab-word 매칭과 일반 승격은 항상 태그 하나(단일 [한자|읽기]) 단위다.
      const ruby = buildRuby(unit.kanji, unit.reading);
      markAsWordCard(ruby, cls.item, cls.kind);
      element.append(ruby);
      i += 1;
      continue;
    }
    // expression: 같은 표현 구간(rangeKey)에 속하는 연속 단위를 한 span으로 묶는다
    // — 조사·태그가 섞여 있어도 팝업 하나만 뜨게.
    const rangeKey = cls.rangeKey;
    const group = [];
    let j = i;
    while (j < units.length) {
      const candidate = units[j];
      if (candidate.type === "br") break;
      const candidateCls = classifyUnit(candidate);
      if (!candidateCls || candidateCls.kind !== "expression" || candidateCls.rangeKey !== rangeKey) break;
      group.push(candidate);
      j += 1;
    }
    const wrapper = document.createElement("span");
    for (const groupUnit of group) {
      wrapper.append(groupUnit.type === "tag" ? buildRuby(groupUnit.kanji, groupUnit.reading) : document.createTextNode(groupUnit.value));
    }
    markAsWordCard(wrapper, cls.item, "expression");
    element.append(wrapper);
    i = j;
  }
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
  setSafeImage(
    $("portrait-image"),
    narrator ? locationBackdrop($("stage").dataset.location) : sceneCharacterImage,
  );
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
      renderAnnotatedText(el, text, sceneVocab, sceneExpr);
      $("portrait").classList.remove("speaking");
      onLineFullyShown();
    }
  }, 22);
}

function onLineFullyShown() {
  const isLastLine = sceneLineIndex >= sceneLines.length - 1;
  if (isLastLine && sceneChoices.length) {
    renderChoices();
    markCurrentSceneSeen();
  } else {
    $("dialogue-next").classList.remove("hidden");
  }
  if (listeningMode) speakCurrentLine();
}

async function markCurrentSceneSeen() {
  if (sceneLearningMarked) return;
  sceneLearningMarked = true;
  try {
    const result = await api("/api/dating-sim/seen", {method:"POST", body:JSON.stringify({story_id:storyId})});
    latestState.learning_progress = result.learning_progress;
    renderHud(latestState);
  } catch (error) {
    sceneLearningMarked = false;
    console.error(error);
  }
}

function advanceLine() {
  if (!recordedAudio.paused || window.speechSynthesis?.speaking) stopListening({ turnOff: false });
  if (typewriterTimer) {
    // 타자기 도중 클릭하면 그 줄을 즉시 완성해서 보여준다.
    stopTypewriter();
    const line = sceneLines[sceneLineIndex];
    renderAnnotatedText($("dialogue-text"), typeof line === "string" ? line : line.text, sceneVocab, sceneExpr);
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
    renderAnnotatedText(label, choice.text, sceneVocab, sceneExpr);
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
  sceneExpr = state.scene.expressions_used || [];
  sceneLineIndex = 0;
  sceneLearningMarked = false;
  $("stage").dataset.location = state.scene.location;
  $("stage").dataset.day = state.day;
  sceneCharacterImage = state.scene.character_image || state.character_image || "";
  setSafeImage($("portrait-image"), sceneCharacterImage);
  showView("scene-view");
  updateListeningControls(listeningMode ? "대기 중" : "꺼짐");
  typeLine(sceneLines[0]);
}

function renderChoiceResult(state) {
  const delta = state.choice_result.affection_delta;
  renderAnnotatedText($("result-speaker-name"), state.character_name);
  $("stage").dataset.location = state.choice_result.location || "result";
  $("stage").dataset.day = state.day;
  setSafeImage($("result-portrait-image"), state.choice_result.character_image || state.character_image);
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
  setSafeImage($("ending-portrait-image"), state.character_image);
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
  const learning = encounter.learning_progress;
  return encounter.completed
    ? `엔딩 · ${encounter.ending_title}`
    : `${learning?.total ? `학습 ${learning.seen}/${learning.total} · ${learning.percent}%` : "학습 진행 0%"} · 호감도 ${encounter.affection}`;
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
  probeStoryListForAdmin();
}

// ── 관리자 전용: 진행 가능한(시나리오·이미지 준비 완료) 미연시 목록 팝오버 ──
let playableStories = null;

async function loadPlayableStories(force = false) {
  if (!playableStories || force) playableStories = await api("/api/dating-sim/playable-stories");
  return playableStories;
}

// 로비에는 관리자 여부가 없으므로 목록 API가 성공할 때만(=관리자) 버튼을 보여준다.
async function probeStoryListForAdmin() {
  try {
    await loadPlayableStories();
    $("lobby-story-list-btn").classList.remove("hidden");
  } catch (_) {
    $("lobby-story-list-btn").classList.add("hidden");
  }
}

function closeStoryPopover() {
  $("story-popover").classList.add("hidden");
}

async function openStoryPopover(anchor) {
  const pop = $("story-popover");
  if (!pop.classList.contains("hidden") && pop.dataset.anchor === anchor.id) return closeStoryPopover();
  pop.dataset.anchor = anchor.id;
  pop.replaceChildren(Object.assign(document.createElement("p"), { className: "story-popover-empty", textContent: "불러오는 중…" }));
  pop.classList.remove("hidden");
  const rect = anchor.getBoundingClientRect();
  const width = Math.min(320, window.innerWidth - 16);
  pop.style.width = `${width}px`;
  pop.style.left = `${Math.max(8, Math.min(rect.left, window.innerWidth - width - 8))}px`;
  pop.style.top = `${rect.bottom + 6}px`;
  let stories;
  try {
    stories = await loadPlayableStories(true);
  } catch (e) {
    pop.replaceChildren(Object.assign(document.createElement("p"), { className: "story-popover-empty", textContent: e.message }));
    return;
  }
  const head = Object.assign(document.createElement("strong"), { textContent: `미연시 ${stories.length}편 (완료 ${stories.filter((s) => s.ready).length}편)` });
  const list = document.createElement("div");
  list.className = "story-popover-list";
  if (!stories.length) {
    list.append(Object.assign(document.createElement("p"), { className: "story-popover-empty", textContent: "서재에 미연시가 없습니다" }));
  }
  for (const item of stories) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "story-popover-item";
    if (item.story_id === storyId) button.classList.add("current");
    if (item.character_image) {
      const img = document.createElement("img");
      img.src = item.character_image;
      img.alt = "";
      img.loading = "lazy";
      button.append(img);
    }
    const name = document.createElement("span");
    name.className = "story-popover-name";
    renderAnnotatedText(name, item.character_name);
    const status = document.createElement("small");
    status.textContent = item.completed ? "엔딩 완료" : item.started ? `DAY ${item.day}/${item.total_days} 진행 중` : "새로 시작";
    if (!item.ready) {
      // 이미지·시나리오가 덜 끝난 작품도 목록에 남기고 무엇이 모자란지 표시한다.
      const missing = [];
      if (!item.scenario_ready) missing.push("시나리오");
      if (!item.images_ready) missing.push(`이미지 ${item.image_count}/42`);
      const badge = document.createElement("em");
      badge.className = "story-popover-badge";
      badge.textContent = `미완료 · ${missing.join(" · ")}`;
      status.append(" ", badge);
      button.classList.add("incomplete");
    }
    const text = document.createElement("span");
    text.className = "story-popover-text";
    text.append(name, status);
    button.append(text);
    button.addEventListener("click", () => {
      closeStoryPopover();
      if (item.story_id !== storyId) enterStory(item.story_id);
    });
    list.append(button);
  }
  pop.replaceChildren(head, list);
}

for (const id of ["story-list-btn", "lobby-story-list-btn"]) {
  $(id).addEventListener("click", (event) => {
    event.stopPropagation();
    openStoryPopover($(id));
  });
}
document.addEventListener("click", (event) => {
  if (!event.target.closest("#story-popover")) closeStoryPopover();
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") closeStoryPopover();
});

function enterStory(nextStoryId) {
  storyId = nextStoryId;
  loadState();
}

async function boot() {
  if (storyId) return loadState();
  showView("loading-view");
  try {
    const encounters = await api("/api/dating-sim/encounters");
    if (!encounters.length) {
      const created = await api("/api/dating-sim/new", { method: "POST" });
      return enterStory(created.story_id);
    }
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
    renderAnnotatedText($("dialogue-text"), typeof line === "string" ? line : line.text, sceneVocab, sceneExpr);
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

function closeTreeImageDetail() {
  stopDatingSimImageGenPoll();
  document.querySelector(".tree-image-detail-overlay")?.remove();
}

// ★ 2026-09-24: "참고이미지 다시추출하기버튼눌러서 참고할수있는 이미지를 내가 직접
// 선택할수있도록 이미지 전부 띄워주고 내가 체크한이미지로 재생성" 요청 — 원작 컷
// 전부를 띄워 최대 4장을 체크하고, 그 컷들로 인물(portrait)만 또는 전체를 다시 만든다.
const MAX_PICKED_REFERENCES = 4;

function buildReferencePicker(item) {
  const wrap = document.createElement("div");
  wrap.className = "reference-picker";
  const openButton = document.createElement("button");
  openButton.type = "button";
  openButton.className = "tree-image-generate-btn";
  openButton.textContent = "🔎 참고 이미지 다시 추출하기";
  const body = document.createElement("div");
  body.className = "reference-picker-body hidden";
  wrap.append(openButton, body);

  openButton.addEventListener("click", async () => {
    if (!body.classList.contains("hidden")) return body.classList.add("hidden");
    body.classList.remove("hidden");
    body.replaceChildren(Object.assign(document.createElement("p"), { className: "tree-image-detail-empty", textContent: "후보를 불러오는 중…" }));
    let data;
    try {
      data = await api(`/api/dating-sim/scenario-tree/reference-candidates${storyQuery()}`);
    } catch (e) {
      body.replaceChildren(Object.assign(document.createElement("p"), { className: "tree-image-detail-empty", textContent: e.message }));
      return;
    }
    const picked = new Set(data.selected);
    const grid = document.createElement("div");
    grid.className = "tree-image-reference-grid reference-picker-grid";
    const counter = document.createElement("p");
    counter.className = "tree-image-detail-empty";
    const status = document.createElement("span");
    status.className = "tree-image-generate-status";
    const buttons = [];
    const refresh = () => {
      counter.textContent = `원작 컷 ${data.candidates.length}장 중 ${picked.size}/${MAX_PICKED_REFERENCES}장 선택`
        + (data.selected.length ? " · 지금은 직접 고른 사진을 쓰는 중" : " · 지금은 자동 선별 중");
      for (const b of buttons) if (b.needsPick) b.el.disabled = picked.size === 0;
    };
    for (const candidate of data.candidates) {
      const label = document.createElement("label");
      label.className = "reference-picker-item";
      const box = document.createElement("input");
      box.type = "checkbox";
      box.checked = picked.has(candidate.name);
      const img = document.createElement("img");
      img.src = candidate.url;
      img.loading = "lazy";
      img.alt = candidate.name;
      box.addEventListener("change", () => {
        if (box.checked && picked.size >= MAX_PICKED_REFERENCES) {
          box.checked = false;
          status.textContent = `최대 ${MAX_PICKED_REFERENCES}장까지 고를 수 있어요`;
          return;
        }
        status.textContent = "";
        if (box.checked) picked.add(candidate.name); else picked.delete(candidate.name);
        label.classList.toggle("picked", box.checked);
        refresh();
      });
      label.classList.toggle("picked", box.checked);
      label.append(img, box);
      grid.append(label);
    }
    const actions = document.createElement("div");
    actions.className = "tree-image-generate";
    const setBusy = (busy) => { for (const b of buttons) b.el.disabled = busy || (b.needsPick && picked.size === 0); };
    let tick;
    const run = (extra, label) => () => {
      const params = new URLSearchParams(extra);
      for (const name of picked) if (extra.__pick) params.append("reference", name);
      params.delete("__pick");
      startDatingSimImageJob(status, setBusy, tick, params, `${label} 시작 중...`, `${label} 중... (몇 분 걸릴 수 있어요)`);
    };
    const defs = [
      ["✅ 체크한 사진으로 인물만 재생성", { __pick: "1" }, "인물 재생성", true],
      ["✅ 체크한 사진으로 전체 재생성", { __pick: "1", force: "true" }, "전체 재생성", true],
      ["↩️ 자동 선별로 되돌리기", { auto_references: "true" }, "자동 선별 인물 재생성", false],
    ];
    for (const [text, extra, label, needsPick] of defs) {
      const el = document.createElement("button");
      el.type = "button";
      el.className = "tree-image-generate-btn";
      el.textContent = text;
      el.addEventListener("click", run(extra, label));
      buttons.push({ el, needsPick });
      actions.append(el);
    }
    actions.append(status);
    tick = watchDatingSimImageJob(status, setBusy, async () => {
      closeTreeImageDetail();
      await openScenarioTree();
    });
    body.replaceChildren(counter, grid, actions);
    refresh();
    tick(true);
  });
  return wrap;
}

function openTreeImageDetail(item) {
  closeTreeImageDetail();
  const overlay = document.createElement("div");
  overlay.className = "tree-image-detail-overlay";
  overlay.setAttribute("role", "dialog");
  overlay.setAttribute("aria-modal", "true");
  overlay.setAttribute("aria-label", `${item.label || "생성 이미지"} 생성 정보`);

  const panel = document.createElement("div");
  panel.className = "tree-image-detail";
  const head = document.createElement("div");
  head.className = "tree-image-detail-head";
  const title = document.createElement("strong");
  title.textContent = item.label || "생성 이미지";
  const close = document.createElement("button");
  close.type = "button";
  close.className = "history-close-btn";
  close.setAttribute("aria-label", "이미지 생성 정보 닫기");
  close.textContent = "×";
  close.addEventListener("click", closeTreeImageDetail);
  head.append(title, close);

  const resultBlock = document.createElement("section");
  const resultLabel = document.createElement("h3");
  resultLabel.textContent = "생성 결과";
  const result = document.createElement("img");
  result.src = item.image_url;
  result.alt = `${item.label || "장면"} 생성 결과`;
  resultBlock.append(resultLabel, result);
  panel.append(head, resultBlock);

  // ★ 2026-09-23: "사진눌렀을때 이사진만 재생성하기 버튼있게해줘" 요청 —
  // 이 사진 하나(item.key = "portrait" 또는 장면 키)만 강제로 다시 만든다.
  if (item.key) {
    const regenWrap = document.createElement("div");
    regenWrap.className = "tree-image-generate";
    const regenButton = document.createElement("button");
    regenButton.type = "button";
    regenButton.className = "tree-image-generate-btn tree-image-regenerate-btn";
    regenButton.textContent = "🔁 이 사진만 재생성하기";
    const regenStatus = document.createElement("span");
    regenStatus.className = "tree-image-generate-status";
    regenWrap.append(regenButton, regenStatus);
    panel.append(regenWrap);

    const tick = watchDatingSimImageJob(regenStatus, (busy) => { regenButton.disabled = busy; }, async () => {
      closeTreeImageDetail();
      await openScenarioTree();
    });
    regenButton.addEventListener("click", () => startDatingSimImageJob(
      regenStatus, (busy) => { regenButton.disabled = busy; }, tick, { force_key: item.key },
      "재생성 시작 중...", "재생성 중... (몇 분 걸릴 수 있어요)",
    ));
    tick(true);
  }

  const referenceBlock = document.createElement("section");
  const referenceLabel = document.createElement("h3");
  // ★ 2026-09-23: "시나리오트리에서 무슨사진 참조해서 인물생성했는지 참조한
  // 이미지들 확인할수있게해줘" 요청 — 고정 인물 레퍼런스가 여러 장(최대
  // 4장) 평균으로 바뀌어서, 있으면 전부 나열한다(단일 레퍼런스였던 기존
  // 기록은 reference_urls가 1개짜리 배열로 자연히 대체된다).
  const referenceUrls = item.reference_urls?.length ? item.reference_urls : (item.reference_url ? [item.reference_url] : []);
  referenceLabel.textContent = referenceUrls.length > 1
    ? `생성 당시 참고 이미지 (${referenceUrls.length}장 평균)` : "생성 당시 참고 이미지";
  referenceBlock.append(referenceLabel);
  if (referenceUrls.length) {
    const grid = document.createElement("div");
    grid.className = "tree-image-reference-grid";
    referenceUrls.forEach((url, index) => {
      const reference = document.createElement("img");
      reference.src = url;
      reference.alt = referenceUrls.length > 1
        ? `${item.label || "장면"} 참고 이미지 ${index + 1}/${referenceUrls.length}`
        : `${item.label || "장면"} 생성 참고 이미지`;
      grid.append(reference);
    });
    referenceBlock.append(grid);
  } else {
    const empty = document.createElement("p");
    empty.className = "tree-image-detail-empty";
    empty.textContent = "참고 이미지 없이 생성했거나 이전 기록에 참고 파일이 남아 있지 않습니다.";
    referenceBlock.append(empty);
  }
  panel.append(referenceBlock);
  referenceBlock.append(buildReferencePicker(item));

  const info = document.createElement("section");
  const infoLabel = document.createElement("h3");
  infoLabel.textContent = "원본 계획 프롬프트";
  const provider = document.createElement("p");
  provider.className = "tree-image-provider";
  provider.textContent = item.provider ? `생성기: ${item.provider}` : "생성기 기록 없음";
  const prompt = document.createElement("pre");
  prompt.textContent = item.prompt || "이 이미지는 이전 형식으로 생성되어 당시 프롬프트가 매니페스트에 기록되지 않았습니다.";
  info.append(infoLabel, provider, prompt);
  panel.append(info);

  if (item.effective_prompt) {
    const effective = document.createElement("section");
    const effectiveLabel = document.createElement("h3");
    effectiveLabel.textContent = "ComfyUI에 실제 전달된 프롬프트";
    const effectiveText = document.createElement("pre");
    effectiveText.textContent = item.effective_prompt;
    effective.append(effectiveLabel, effectiveText);
    panel.append(effective);
  }

  const settingsEntries = Object.entries(item.generation_settings || {});
  if (settingsEntries.length) {
    const settings = document.createElement("section");
    settings.className = "tree-image-settings-section";
    const settingsLabel = document.createElement("h3");
    settingsLabel.textContent = "생성 설정";
    const list = document.createElement("dl");
    list.className = "tree-image-settings";
    const labels = {
      model: "모델", loader: "로더", width: "너비", height: "높이", steps: "스텝",
      cfg: "CFG", sampler: "샘플러", scheduler: "스케줄러", denoise: "Denoise",
      vae: "VAE", composition_pass: "구도 합성",
      base_seed: "기본 시드", used_seed: "사용 시드", attempt: "시도 횟수",
    };
    for (const [key, value] of settingsEntries) {
      const dt = document.createElement("dt");
      dt.textContent = labels[key] || key;
      const dd = document.createElement("dd");
      dd.textContent = String(value);
      list.append(dt, dd);
    }
    settings.append(settingsLabel, list);
    panel.append(settings);
  }

  overlay.append(panel);
  overlay.addEventListener("click", (event) => {
    if (event.target === overlay) closeTreeImageDetail();
  });
  document.body.append(overlay);
  close.focus();
}

function makeTreeToggle(title, open = false, className = "") {
  const details = document.createElement("details");
  details.className = `tree-toggle ${className}`.trim();
  details.open = open;
  const summary = document.createElement("summary");
  summary.textContent = title;
  const content = document.createElement("div");
  content.className = "tree-toggle-content";
  details.append(summary, content);
  return { details, summary, content };
}

function renderScenarioImages(body, tree, includeHeading = true) {
  const images = tree.generated_images?.gallery || [];
  if (includeHeading) {
    const head = document.createElement("div");
    head.className = "tree-section-head";
    head.textContent = "🖼️ 생성된 캐릭터·장면 이미지";
    body.append(head);
  }
  if (!images.length) {
    const empty = document.createElement("p");
    empty.className = "tree-report-note";
    empty.textContent = "이 작품에는 아직 생성된 이미지가 없습니다.";
    body.append(empty);
    return;
  }
  const gallery = document.createElement("div");
  gallery.className = "tree-image-gallery";
  for (const item of images) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "tree-image-card";
    button.setAttribute("aria-label", `${item.label} 생성 정보 보기`);
    const image = document.createElement("img");
    image.src = item.image_url;
    image.alt = item.label;
    image.loading = "lazy";
    const label = document.createElement("span");
    label.textContent = item.label;
    button.append(image, label);
    let touchedAt = 0;
    const activate = (event) => {
      event.preventDefault();
      event.stopPropagation();
      openTreeImageDetail(item);
    };
    button.addEventListener("touchend", (event) => {
      touchedAt = Date.now();
      activate(event);
    }, { passive: false });
    button.addEventListener("click", (event) => {
      if (Date.now() - touchedAt < 700) return;
      activate(event);
    });
    gallery.append(button);
  }
  body.append(gallery);
}

function renderScenarioReport(body, tree, includeHeading = true) {
  const report = tree.report;
  if (includeHeading) {
    const head = document.createElement("div");
    head.className = "tree-section-head";
    head.textContent = "📊 작품·시나리오 보고서";
    body.append(head);
  }

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

// ★ 2026-09-23: "시나리오트리에 이미지생성하기 버튼 만들어서 이미지만
// 생성해서 올릴수있게하자" 요청 — 매일 자동 에이전트(run_daily_dating_sim_agent.py)를
// 기다리지 않고 관리자가 지금 바로 이 작품의 이미지 생성만(시나리오는 그대로)
// 수동으로 돌릴 수 있게 한다. 여러 장을 생성하는 작업이라 몇 분 걸릴 수
// 있어서, 서버는 백그라운드로 돌리고 여기서는 시작 후 주기적으로 상태를
// 물어본다.
let datingSimImageGenPollTimer = null;

function stopDatingSimImageGenPoll() {
  if (datingSimImageGenPollTimer) {
    clearInterval(datingSimImageGenPollTimer);
    datingSimImageGenPollTimer = null;
  }
}

// ★ 2026-09-23(같은 날 재요청): "이미이미지가있을때 이미지 재생성 버튼을
// 눙어거 재생성 하게 해줘 이미지전체재생성도 있고 사진눌렀을때 이사진만
// 재생성하기 버튼있게해줘" — 시작/폴링/완료 처리를 세 곳(전체 생성,
// 전체 강제 재생성, 사진 한 장만 재생성)이 공유하도록 공통 함수로 뺐다.
// 서버 쪽 작업은 작품당 하나만 돌 수 있어서(app.py의 _dating_sim_image_jobs)
// 폴링 타이머도 전역 하나만 쓴다.
// ★ 2026-09-24: "미연시 이미지 재생성 완료되면 알람뜨게" 요청 — 화면을 보고 있을 때는 짧은
// 알림음과 안내창으로, 떠나 있을 때는 서버가 보내는 웹 푸시로 알린다.
function notifyImageJobDone() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const osc = ctx.createOscillator();
    osc.frequency.value = 880;
    osc.connect(ctx.destination);
    osc.start();
    osc.stop(ctx.currentTime + 0.25);
  } catch (_) { /* 소리는 선택 사항 */ }
  setTimeout(() => alert("🖼️ 미연시 이미지 재생성이 끝났어요!"), 50);
}

function watchDatingSimImageJob(status, setBusy, onSuccess) {
  let seenRunning = false;
  const tick = async (initial = false) => {
    let data;
    try {
      data = await api(`/api/dating-sim/scenario-tree/generate-images/status${storyQuery()}`);
    } catch (e) {
      stopDatingSimImageGenPoll();
      setBusy(false);
      status.textContent = e.message;
      return;
    }
    if (data.running) {
      seenRunning = true;
      setBusy(true);
      status.textContent = "생성 중... (몇 분 걸릴 수 있어요)";
      if (!datingSimImageGenPollTimer) {
        datingSimImageGenPollTimer = setInterval(tick, 8000);
      }
      return;
    }
    stopDatingSimImageGenPoll();
    setBusy(false);
    if (data.returncode === 0) {
      // initial=true(패널을 막 열었을 때)인데 이번 생애주기에 running을
      // 한 번도 못 봤다면, 예전에 이미 끝난 작업을 지금 처음 조회한
      // 것뿐이므로 새로고침을 또 트리거하지 않는다(무한 루프 방지).
      if (seenRunning || !initial) {
        status.textContent = "완료! 새로고침 중...";
        notifyImageJobDone();
        await onSuccess();
        return;
      }
      status.textContent = "";
      return;
    }
    status.textContent = data.returncode != null
      ? `실패(코드 ${data.returncode}) — 다시 시도해 주세요`
      : "";
  };
  return tick;
}

async function startDatingSimImageJob(status, setBusy, tick, extraParams, startLabel, runningLabel) {
  setBusy(true);
  status.textContent = startLabel;
  try {
    await api(`/api/dating-sim/scenario-tree/generate-images${storyQuery(extraParams)}`, { method: "POST" });
  } catch (e) {
    setBusy(false);
    status.textContent = e.message;
    return;
  }
  status.textContent = runningLabel;
  datingSimImageGenPollTimer = setInterval(tick, 8000);
}

function renderImageGenerationControl(container, tree) {
  const wrap = document.createElement("div");
  wrap.className = "tree-image-generate";
  const genButton = document.createElement("button");
  genButton.type = "button";
  genButton.className = "tree-image-generate-btn";
  genButton.textContent = "🖼️ 이미지 생성하기";

  const hasImages = (tree.generated_images?.gallery || []).length > 0;
  const regenButton = hasImages ? document.createElement("button") : null;
  if (regenButton) {
    regenButton.type = "button";
    regenButton.className = "tree-image-generate-btn tree-image-regenerate-btn";
    regenButton.textContent = "🔁 전체 이미지 재생성";
  }

  const status = document.createElement("span");
  status.className = "tree-image-generate-status";
  wrap.append(genButton);
  if (regenButton) wrap.append(regenButton);
  wrap.append(status);
  container.append(wrap);

  const setBusy = (busy) => {
    genButton.disabled = busy;
    if (regenButton) regenButton.disabled = busy;
  };
  const tick = watchDatingSimImageJob(status, setBusy, openScenarioTree);

  genButton.addEventListener("click", () => startDatingSimImageJob(
    status, setBusy, tick, {}, "생성 시작 중...", "생성 중... (여러 장이라 몇 분 걸릴 수 있어요)"
  ));
  if (regenButton) {
    regenButton.addEventListener("click", () => {
      if (!confirm("이미 만든 이미지를 전부 새로 만듭니다. 시간이 오래 걸릴 수 있어요. 계속할까요?")) return;
      startDatingSimImageJob(
        status, setBusy, tick, { force: "1" },
        "재생성 시작 중...", "재생성 중... (전체라 시간이 오래 걸릴 수 있어요)",
      );
    });
  }

  tick(true);
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

  const imageToggle = makeTreeToggle("🖼️ 생성된 캐릭터·장면 이미지");
  if (tree.source_title) {
    renderImageGenerationControl(imageToggle.content, tree);
  }
  renderScenarioImages(imageToggle.content, tree, false);
  body.append(imageToggle.details);

  if (tree.report) {
    const reportToggle = makeTreeToggle("📊 작품·시나리오 보고서");
    renderScenarioReport(reportToggle.content, tree, false);
    body.append(reportToggle.details);
  }

  const flowToggle = makeTreeToggle("🌳 사건 흐름별 시나리오 트리");
  body.append(flowToggle.details);

  for (const day of tree.days) {
    const dayToggle = makeTreeToggle("", false, "tree-day");
    const dayEl = dayToggle.content;
    const dayHead = dayToggle.summary;
    dayHead.classList.add("tree-day-head");
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
    flowToggle.content.append(dayToggle.details);
  }

  const endingToggle = makeTreeToggle("🏁 엔딩 분기 (누적 호감도)");
  const endings = endingToggle.content;
  endings.classList.add("tree-endings");
  for (const ending of tree.endings) {
    const e = document.createElement("div");
    e.className = "tree-ending";
    e.textContent = `호감도 ${ending.min_affection}+ → ${ending.title}`;
    endings.append(e);
  }
  body.append(endingToggle.details);
}

async function openScenarioTree() {
  stopDatingSimImageGenPoll();
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
  closeTreeImageDetail();
  stopDatingSimImageGenPoll();
  $("tree-overlay").classList.add("hidden");
});
$("tree-overlay").addEventListener("click", (event) => {
  if (event.target === $("tree-overlay")) {
    stopDatingSimImageGenPoll();
    $("tree-overlay").classList.add("hidden");
  }
});
document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") return;
  if (document.querySelector(".tree-image-detail-overlay")) {
    closeTreeImageDetail();
  } else if (document.querySelector(".image-lightbox-overlay")) {
    closeImageLightbox();
  }
});

updateListeningControls();
loadAudioManifest().finally(boot);
