const $ = (id) => document.getElementById(id);
const audio = $("audio");
let audioFile = null;
let audioUrl = "";
let lyricRows = [];
let activeLyric = -1;
let followLyrics = true;
let currentLrc = "";
let remoteTrack = null;
let playlist = [];
let playlistIndex = -1;
let shufflePlaylist = false;
let shuffleHistory = [];
let shuffleHistoryCursor = -1;
let repeatMode = "all";
let activePlaylistName = "";
let pendingResumeTime = 0;
let lastPlaybackSaveAt = 0;
let reviewRunning = false;
const monitoringLrcJobs = new Set();
let favoritesOnly = false;
let playlistViewMode = "all";
let syncedFavorites = [];
const filenameSorter = new Intl.Collator("ko", { numeric: true, sensitivity: "base" });
const RECENT_PLAYLIST_KEY = "natum-mp3-recent-playlist-v1";
const PLAYLIST_PROGRESS_KEY = "natum-mp3-playlist-progress-v1";
const LYRIC_SIZE_KEY = "natum-mp3-active-lyric-size-v1";
const LYRICS_COLLAPSED_KEY = "natum-mp3-lyrics-collapsed-v1";
const LRC_REVIEW_QUEUE_KEY = "natum-mp3-lrc-review-queue-v1";
const ACTIVE_LRC_JOBS_KEY = "natum-mp3-active-lrc-jobs-v1";
const LAST_LRC_FAILURE_KEY = "natum-mp3-last-lrc-failure-v1";
const FAVORITES_KEY = "natum-mp3-favorites-v1";
const THEME_KEY = "natum-mp3-theme-v1";
const PLAYLIST_FILTER_KEY = "natum-mp3-playlist-filter-v1";
const PLAYBACK_MODE_KEY = "natum-mp3-playback-mode-v1";
const PLAYBACK_SESSION_KEY = "natum-mp3-playback-session-v2";
const LYRICS_STUDY_CACHE_KEY = "natum-mp3-lyrics-study-v2";
const RECOMMENDATIONS_RETURN_KEY = "natum-mp3-recommendations-return-v1";
const LYRIC_SIZES = ["normal", "large", "xlarge"];
const LYRIC_SIZE_LABELS = { normal: "보통", large: "크게", xlarge: "아주 크게" };
let lyricsStudyTarget = null;
let landscapeSwipe = null;
let suppressLyricClickUntil = 0;
let macLibraryMatchPromise = null;
let currentLrcFailure = null;
let lyricsStudyPollTimer = 0;
let recommendationCursor = null;
let recommendationLoading = false;
let recommendationTotal = 0;
let recommendationItems = [];
const collapsedRecommendationGroups = new Set();
let lyricsStudyKey = "";
const lyricsStudyRecoveryInFlight = new Set();
let lyricFitFrame = 0;
let favoritesSyncBusy = false;
let favoritesKnownCount = 0;

function setTheme(theme) {
  const selected = theme === "dark" ? "dark" : "light";
  document.documentElement.dataset.theme = selected;
  const button = $("theme-toggle");
  button.textContent = selected === "dark" ? "라이트" : "다크";
  button.setAttribute("aria-label", selected === "dark" ? "라이트 모드로 전환" : "다크 모드로 전환");
  localStorage.setItem(THEME_KEY, selected);
}

function message(text, error = false) {
  const box = $("status");
  box.textContent = text;
  box.style.background = error ? "#9a2f48" : "";
  box.classList.remove("hidden");
  clearTimeout(message.timer);
  message.timer = setTimeout(() => box.classList.add("hidden"), error ? 5000 : 3000);
}

function clock(seconds) {
  if (!Number.isFinite(seconds)) return "0:00";
  const value = Math.max(0, Math.floor(seconds));
  return `${Math.floor(value / 60)}:${String(value % 60).padStart(2, "0")}`;
}

function setCurrentTrackTitle(title) {
  const value = String(title || "").trim() || "재생할 곡을 선택하세요";
  $("landscape-track-title").textContent = value;
}

function updateGenerateButton() {
  $("generate").textContent = currentLrc ? "LRC 재생성" : "LRC 생성";
}

function detectLyricsStudyTarget() {
  const text = lyricRows.map((row) => row.text).join("\n");
  const item = playlistIndex >= 0 ? playlist[playlistIndex] : (remoteTrack || audioFile);
  const resolved = resolveTrackLyricsLanguage(item, text);
  if (resolved.mismatch) return null;
  const language = resolved.language;
  if (language === "ja") {
    return { language: "일본어", persona: "일본어 선생님", label: "일본어 가사 직해 요청" };
  }
  if (language === "en") {
    return { language: "영어", persona: "영어 선생님", label: "영어 가사 직해 요청" };
  }
  return null;
}

function detectLyricsLanguage(text) {
  const hangul = (text.match(/[가-힣]/g) || []).length;
  const kana = (text.match(/[ぁ-ゖァ-ヺー]/g) || []).length;
  const latin = (text.match(/[A-Za-z]/g) || []).length;
  if (kana >= 2 && kana >= hangul * 0.35) return "ja";
  if (hangul >= 2 && hangul >= latin * 0.15) return "ko";
  if (latin >= 20 && latin > kana * 3) return "en";
  return "unknown";
}

function detectTrackLanguageHint(item) {
  const label = `${trackFilename(item)} ${item?.title || ""}`;
  const hangul = (label.match(/[가-힣]/g) || []).length;
  const kana = (label.match(/[ぁ-ゖァ-ヺ]/g) || []).length;
  if (kana >= 2) return "ja";
  if (hangul >= 4 && kana === 0 && !/(?:일본어|일본곡|j-?pop)/i.test(label)) return "ko";
  return "unknown";
}

function resolveTrackLyricsLanguage(item, text) {
  const lyricsLanguage = detectLyricsLanguage(text);
  const titleLanguage = detectTrackLanguageHint(item);
  const mismatch = titleLanguage === "ko" && lyricsLanguage === "ja";
  return {
    language: mismatch ? "ko" : (lyricsLanguage === "unknown" ? titleLanguage : lyricsLanguage),
    lyricsLanguage,
    titleLanguage,
    mismatch,
  };
}

function compactHash(value) {
  let hash = 2166136261;
  for (const character of String(value || "")) {
    hash ^= character.codePointAt(0);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0).toString(36);
}

function getLyricsStudyCache() {
  try {
    const value = JSON.parse(localStorage.getItem(LYRICS_STUDY_CACHE_KEY) || "{}");
    return value && typeof value === "object" ? value : {};
  } catch (_) { return {}; }
}

function saveLyricsStudyRecord(key, record) {
  const cache = getLyricsStudyCache();
  cache[key] = record;
  const entries = Object.entries(cache).sort((left, right) => Number(right[1]?.updatedAt || 0) - Number(left[1]?.updatedAt || 0));
  try { localStorage.setItem(LYRICS_STUDY_CACHE_KEY, JSON.stringify(Object.fromEntries(entries.slice(0, 30)))); } catch (_) {}
}

function currentLyricsStudyKey(target = lyricsStudyTarget) {
  if (!target || !lyricRows.length) return "";
  return `${target.language}:${compactHash(currentLyricsStudyTrackIdentity())}`;
}

function currentLyricsStudyTrackIdentity() {
  const item = currentReviewTrack();
  const youtubeId = trackYoutubeId(item);
  if (youtubeId) return `youtube:${youtubeId}`;
  const filename = trackFilename(item).replace(/\.mp3$/i, "");
  const title = $("title").textContent.trim() || "제목 없는 곡";
  return `title:${normalizedTrackName(filename || title)}`;
}

async function recoverLyricsStudyRecord(key) {
  if (!key || key !== lyricsStudyKey || lyricsStudyRecoveryInFlight.has(key)) return;
  lyricsStudyRecoveryInFlight.add(key);
  try {
    const params = new URLSearchParams({
      track_key: currentLyricsStudyTrackIdentity(),
      title: $("title").textContent.trim() || "제목 없는 곡",
      language: lyricsStudyTarget?.language || "",
    });
    const response = await fetch(`/api/mp3/lyrics-study/history?${params}`, {
      credentials: "same-origin",
      cache: "no-store",
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || !data.found || key !== lyricsStudyKey) return;
    const complete = data.status === "done" && String(data.result || "").trim();
    const record = {
      status: complete ? "complete" : data.status === "failed" ? "failed" : data.status === "processing" ? "processing" : "pending",
      stage: complete ? "직해 완료" : data.status === "failed" ? "직해 실패" : "이전 요청 확인 중",
      percent: complete ? 100 : 5,
      estimated: !complete,
      sourceMessageId: Number(data.source_message_id),
      result: complete ? String(data.result).trim() : "",
      title: data.title || $("title").textContent.trim(),
      language: data.language || lyricsStudyTarget?.language,
      updatedAt: Date.now(),
    };
    saveLyricsStudyRecord(key, record);
    setLyricsStudyUi(record);
    if (["pending", "processing"].includes(record.status)) scheduleLyricsStudyPoll(key, 300);
  } catch (_) {
    // 서버 기록을 읽지 못해도 로컬 재생과 새 직해 요청은 그대로 사용할 수 있다.
  } finally {
    lyricsStudyRecoveryInFlight.delete(key);
  }
}

function formatRemainingTime(seconds) {
  const value = Math.max(0, Math.round(Number(seconds || 0)));
  if (value < 60) return `약 ${Math.max(1, value)}초 후`;
  return `약 ${Math.ceil(value / 60)}분 후`;
}

function setLyricsStudyProgress(record = null) {
  const progress = $("lyrics-study-progress");
  const running = record?.status === "pending" || record?.status === "processing";
  const visible = running || record?.status === "failed";
  progress.classList.toggle("hidden", !visible);
  if (!visible) return;
  const percent = Math.max(0, Math.min(100, Number(record.percent || (record.status === "pending" ? 5 : 0))));
  $("lyrics-study-stage").textContent = record.stage || (record.status === "failed" ? "직해 실패" : "요청 대기 중");
  $("lyrics-study-percent").textContent = record.estimated && running ? `예상 ${percent}%` : `${percent}%`;
  $("lyrics-study-progress-bar").style.width = `${percent}%`;
  $("lyrics-study-progress-track").setAttribute("aria-valuenow", String(percent));
  if (record.status === "pending" && Number(record.queuePosition || 0) > 0) {
    $("lyrics-study-eta").textContent = Number(record.etaSeconds || 0) > 0
      ? `대기열 ${record.queuePosition}번째 · ${formatRemainingTime(record.etaSeconds)}`
      : "AI 사용 한도가 회복되면 자동으로 재개합니다.";
  } else if (record.status === "processing") {
    $("lyrics-study-eta").textContent = `경과 ${clock(record.elapsedSeconds || 0)} · ${formatRemainingTime(record.etaSeconds)}`;
  } else {
    $("lyrics-study-eta").textContent = record.error || "다시 요청하면 재시도합니다.";
  }
}

function renderLyricsStudyResult(text = "") {
  const result = $("lyrics-translation-result");
  result.replaceChildren();
  if (!text) return;
  const pattern = /([\p{Script=Han}々〆ヵヶ]+)[(（]([ぁ-ゖァ-ヺー・]+)[)）]/gu;
  let cursor = 0;
  for (const match of text.matchAll(pattern)) {
    if (match.index > cursor) result.append(document.createTextNode(text.slice(cursor, match.index)));
    const ruby = document.createElement("ruby");
    ruby.append(document.createTextNode(match[1]));
    const reading = document.createElement("rt");
    reading.textContent = match[2];
    ruby.append(reading);
    result.append(ruby);
    cursor = match.index + match[0].length;
  }
  if (cursor < text.length) result.append(document.createTextNode(text.slice(cursor)));
}

function setLyricsStudyUi(record = null) {
  const button = $("lyrics-study");
  const state = $("lyrics-translation-state");
  const result = $("lyrics-translation-result");
  const details = $("lyrics-translation");
  const pending = record?.status === "pending" || record?.status === "processing";
  const complete = record?.status === "complete" && record?.result;
  button.disabled = pending;
  button.textContent = pending ? "가사 직해 중…" : complete ? "가사 직해 다시 요청" : lyricsStudyTarget?.label || "";
  state.textContent = pending ? (record.stage || "답변 기다리는 중") : complete ? "완료" : record?.status === "failed" ? "실패" : "결과 없음";
  renderLyricsStudyResult(complete ? record.result : "");
  setLyricsStudyProgress(record);
  if (pending || complete) details.open = true;
}

function stopLyricsStudyPolling() {
  clearTimeout(lyricsStudyPollTimer);
  lyricsStudyPollTimer = 0;
}

function scheduleLyricsStudyPoll(key, delay = 1800) {
  stopLyricsStudyPolling();
  lyricsStudyPollTimer = window.setTimeout(() => pollLyricsStudyResult(key), delay);
}

async function pollLyricsStudyResult(key) {
  if (!key || key !== lyricsStudyKey) return;
  const record = getLyricsStudyCache()[key];
  if (!record || !["pending", "processing"].includes(record.status) || !record.sourceMessageId) return;
  try {
    const response = await fetch(`/api/mp3/lyrics-study/status?source_message_id=${encodeURIComponent(record.sourceMessageId)}`, {
      credentials: "same-origin",
      cache: "no-store",
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error("response unavailable");
    if (data.status === "done" && String(data.result || "").trim()) {
      const complete = { ...record, status: "complete", result: String(data.result).trim(), percent: 100, stage: "직해 완료", updatedAt: Date.now() };
      saveLyricsStudyRecord(key, complete);
      if (key === lyricsStudyKey) setLyricsStudyUi(complete);
      message("가사 직해가 완료되었습니다.");
      return;
    }
    if (data.status === "failed") {
      const failed = { ...record, status: "failed", stage: data.stage || "직해 실패", error: data.error || "직해를 완료하지 못했습니다", percent: 0, updatedAt: Date.now() };
      saveLyricsStudyRecord(key, failed);
      if (key === lyricsStudyKey) setLyricsStudyUi(failed);
      return;
    }
    const updated = {
      ...record,
      status: data.status === "processing" ? "processing" : "pending",
      stage: data.stage,
      percent: Number(data.percent || 0),
      estimated: Boolean(data.estimated),
      queuePosition: Number(data.queue_position || 0),
      elapsedSeconds: Number(data.elapsed_seconds || 0),
      etaSeconds: Number(data.eta_seconds || 0),
      updatedAt: Date.now(),
    };
    saveLyricsStudyRecord(key, updated);
    if (key === lyricsStudyKey) setLyricsStudyUi(updated);
  } catch (_) {
    if (key === lyricsStudyKey) $("lyrics-translation-state").textContent = "연결 후 자동 확인";
  }
  if (key === lyricsStudyKey) scheduleLyricsStudyPoll(key, 1800);
}

function updateLyricsStudyButton() {
  lyricsStudyTarget = detectLyricsStudyTarget();
  const section = $("lyrics-translation");
  const nextKey = currentLyricsStudyKey(lyricsStudyTarget);
  section.classList.toggle("hidden", !nextKey);
  if (!nextKey) {
    lyricsStudyKey = "";
    stopLyricsStudyPolling();
    setLyricsStudyUi();
    return;
  }
  if (lyricsStudyKey !== nextKey) stopLyricsStudyPolling();
  lyricsStudyKey = nextKey;
  const record = getLyricsStudyCache()[nextKey] || null;
  setLyricsStudyUi(record);
  if (["pending", "processing"].includes(record?.status)) scheduleLyricsStudyPoll(nextKey, 300);
  else if (!record) recoverLyricsStudyRecord(nextKey);
}

async function requestLyricsStudy() {
  const target = detectLyricsStudyTarget();
  const lyrics = lyricRows.map((row) => row.text).join("\n").trim();
  if (!target || !lyrics) return;
  const button = $("lyrics-study");
  const title = $("title").textContent.trim() || "제목 없는 곡";
  const directions = target.language === "일본어"
    ? "가사 순서를 그대로 지키며 각 일본어 원문 바로 아래에 자연스러운 한국어 직해를 붙여주세요. 한자가 있는 줄에는 읽기 어려운 말만 괄호로 후리가나를 덧붙이되, 문법 수업·새 예문·감상 평가는 넣지 마세요."
    : "가사 순서를 그대로 지키며 각 영어 원문 바로 아래에 자연스러운 한국어 직해를 붙여주세요. 문법 수업·새 예문·감상 평가는 넣지 마세요.";
  const trackIdentity = currentLyricsStudyTrackIdentity();
  const content = `[MP3 가사 직해 요청]\n곡: ${title}\n곡 식별자: ${trackIdentity}\n언어: ${target.language}\n\n${directions}\n반복되는 가사도 생략하지 말고 입력된 순서대로 옮겨주세요. LRC 또는 Whisper 오인식으로 의심되는 대목도 별도의 검수 문구를 붙이지 말고, 입력된 원문을 유지한 채 가능한 범위에서 자연스럽게 직해해주세요.\n\n[가사]\n${lyrics.slice(0, 16000)}`;
  const key = currentLyricsStudyKey(target);
  button.disabled = true;
  button.textContent = "가사 직해 요청 중…";
  $("lyrics-translation").open = true;
  try {
    const response = await fetch("/api/messages", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ room_id: target.persona, content }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || "가사 직해 요청을 보내지 못했습니다");
    if (!data.source_message_id) throw new Error("직해 요청 번호를 확인하지 못했습니다");
    const record = {
      status: "pending",
      stage: "요청 대기 중",
      percent: 5,
      estimated: true,
      queuePosition: 1,
      elapsedSeconds: 0,
      etaSeconds: 45,
      sourceMessageId: Number(data.source_message_id),
      persona: target.persona,
      language: target.language,
      title,
      requestedAt: Date.now(),
      updatedAt: Date.now(),
    };
    lyricsStudyKey = key;
    saveLyricsStudyRecord(key, record);
    setLyricsStudyUi(record);
    scheduleLyricsStudyPoll(key, 1200);
    message("가사 직해를 요청했습니다. 이 화면에서 완료 결과를 보여드립니다.");
  } catch (error) {
    button.disabled = false;
    button.textContent = target.label;
    $("lyrics-translation-state").textContent = "요청 실패";
    message(error.message, true);
  }
}

function attachLrcToCurrentTrack(text) {
  const item = playlistIndex >= 0 ? playlist[playlistIndex] : null;
  if (!item || !text) return;
  const filename = trackFilename(item);
  if (!filename) return;
  const name = filename.replace(/\.mp3$/i, ".lrc");
  item.lrcFile = new File([text], name, { type: "text/plain;charset=utf-8" });
  item.has_lrc = true;
  if (item.stream_url?.includes("favorites-library")) {
    item.lrc_url = `/api/mp3-player/favorites-library/${encodeURIComponent(item.id)}/lrc`;
  } else if (item.stream_url?.includes("/api/mp3-player/library/")) {
    item.lrc_url = `/api/mp3-player/library/${encodeURIComponent(item.id)}/lrc`;
  }
  const resolved = resolveTrackLyricsLanguage(item, text);
  item.lyricsLanguage = resolved.language;
  item.lrcLanguageMismatch = resolved.mismatch;
}

function showLrcProgress(stage, detail, percent = null, indeterminate = false) {
  const panel = $("lrc-progress");
  panel.classList.remove("hidden");
  panel.classList.toggle("indeterminate", indeterminate);
  $("lrc-progress-stage").textContent = stage;
  $("lrc-progress-detail").textContent = detail;
  const value = percent == null ? 0 : Math.max(0, Math.min(100, percent));
  $("lrc-progress-bar").style.width = `${value}%`;
  const track = panel.querySelector('[role="progressbar"]');
  track.setAttribute("aria-valuenow", String(value));
  track.setAttribute("aria-label", `${stage} ${detail}`);
}

function lrcEtaText(status) {
  const remaining = Number(status.estimated_remaining_seconds);
  const completion = Date.parse(status.estimated_completion_at || "");
  if (!Number.isFinite(remaining) || remaining < 0 || !Number.isFinite(completion)) {
    return status.status === "running" ? "예상 완료시간 계산 중" : "";
  }
  const time = new Intl.DateTimeFormat("ko-KR", { hour: "2-digit", minute: "2-digit", hour12: false }).format(new Date(completion));
  const remainingText = remaining >= 3600
    ? `${Math.floor(remaining / 3600)}시간 ${Math.ceil((remaining % 3600) / 60)}분`
    : remaining >= 60 ? `${Math.ceil(remaining / 60)}분` : "1분 이내";
  return `예상 완료 ${time} · 약 ${remainingText} 남음`;
}

function getActiveLrcJobs() {
  try {
    const parsed = JSON.parse(localStorage.getItem(ACTIVE_LRC_JOBS_KEY) || "[]");
    return Array.isArray(parsed) ? parsed : [];
  } catch (_) { return []; }
}

function saveActiveLrcJobs(jobs) {
  try { localStorage.setItem(ACTIVE_LRC_JOBS_KEY, JSON.stringify(jobs.slice(-30))); } catch (_) {}
}

function rememberLrcJob(job, file) {
  const filename = trackFilename(file) || "audio.mp3";
  const key = playlistIndex >= 0 ? reviewTrackKey(playlist[playlistIndex]) : filename;
  const jobs = getActiveLrcJobs().filter((entry) => entry.id !== job.id);
  jobs.push({ id: job.id, key, title: filename.replace(/\.mp3$/i, ""), filename, status: job.status, createdAt: Date.now() });
  saveActiveLrcJobs(jobs);
}

function updateRememberedLrcJob(jobId, updates) {
  const jobs = getActiveLrcJobs();
  const target = jobs.find((entry) => entry.id === jobId);
  if (target) Object.assign(target, updates);
  saveActiveLrcJobs(jobs);
}

function forgetRememberedLrcJob(jobId) {
  saveActiveLrcJobs(getActiveLrcJobs().filter((entry) => entry.id !== jobId));
}

function showLrcFailure(entry, status) {
  currentLrcFailure = { ...entry, ...status, id: status.id || entry.id };
  try { localStorage.setItem(LAST_LRC_FAILURE_KEY, JSON.stringify(currentLrcFailure)); } catch (_) {}
  const reused = Number(status.reused_chunks || 0);
  const detail = reused
    ? `완료된 ${reused}개 조각 보존 · 실패 지점부터 재시도할 수 있습니다`
    : (status.message || "LRC 생성에 실패했습니다");
  showLrcProgress("LRC 생성 중단", detail, 0);
  $("lrc-failure-actions").classList.remove("hidden");
  $("lrc-retry").disabled = status.retryable === false;
}

function dismissLrcFailure() {
  if (currentLrcFailure?.id) forgetRememberedLrcJob(currentLrcFailure.id);
  currentLrcFailure = null;
  try { localStorage.removeItem(LAST_LRC_FAILURE_KEY); } catch (_) {}
  $("lrc-failure-actions").classList.add("hidden");
  $("lrc-progress").classList.add("hidden");
}

async function retryLrcFailure() {
  if (!currentLrcFailure?.id) return;
  const button = $("lrc-retry");
  button.disabled = true;
  try {
    const response = await fetch(`/api/mp3-player/lrc-jobs/${encodeURIComponent(currentLrcFailure.id)}/retry`, {
      method: "POST", credentials: "same-origin",
    });
    const job = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(job.detail || "LRC 재시도를 시작하지 못했습니다");
    $("lrc-failure-actions").classList.add("hidden");
    updateRememberedLrcJob(job.id, { status: "queued" });
    currentLrcFailure = null;
    try { localStorage.removeItem(LAST_LRC_FAILURE_KEY); } catch (_) {}
    const text = await waitForLrcJob(job, null);
    const entry = getActiveLrcJobs().find((item) => item.id === job.id);
    if (entry) updateRememberedLrcJob(job.id, { status: "complete", resultText: text });
    await recoverLrcJobs();
  } catch (error) {
    button.disabled = false;
    message(error.message, true);
  }
}

async function waitForLrcJob(job, file) {
  if (file) rememberLrcJob(job, file);
  for (;;) {
    const response = await fetch(`/api/mp3-player/lrc-jobs/${encodeURIComponent(job.id)}`, { credentials: "same-origin", cache: "no-store" });
    const status = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(status.detail || "LRC 작업 상태를 확인하지 못했습니다");
    updateRememberedLrcJob(job.id, { status: status.status });
    const createdAt = Date.parse(status.created_at || "") || Date.now();
    const elapsed = Math.max(0, Math.floor((Date.now() - createdAt) / 1000));
    const eta = lrcEtaText(status);
    const progressDetail = `${status.message || "Mac에서 처리하고 있습니다"} · 경과 ${clock(elapsed)} · ${Number(status.percent || 0)}%${eta ? ` · ${eta}` : ""}`;
    showLrcProgress(status.stage || "백그라운드 생성 중", progressDetail, Number(status.percent || 0), status.status === "queued");
    if (status.status === "failed") {
      const entry = getActiveLrcJobs().find((item) => item.id === job.id) || { id: job.id, title: status.filename || "이 곡" };
      forgetRememberedLrcJob(job.id);
      showLrcFailure(entry, status);
      throw new Error(status.message || "LRC 생성에 실패했습니다");
    }
    if (status.status === "complete") {
      const result = await fetch(`/api/mp3-player/lrc-jobs/${encodeURIComponent(job.id)}/result`, { credentials: "same-origin", cache: "no-store" });
      if (!result.ok) throw new Error("완성된 LRC를 불러오지 못했습니다");
      const text = await result.text();
      updateRememberedLrcJob(job.id, { status: "complete", resultText: text });
      return text;
    }
    await new Promise((resolve) => setTimeout(resolve, 2500));
  }
}

function removeActiveLrcJobsForKey(key) {
  if (!key) return;
  saveActiveLrcJobs(getActiveLrcJobs().filter((entry) => entry.key !== key));
}

async function recoverLrcJobs() {
  const jobs = getActiveLrcJobs();
  for (const entry of jobs) {
    try {
      let text = entry.resultText || "";
      if (!text) {
        const response = await fetch(`/api/mp3-player/lrc-jobs/${encodeURIComponent(entry.id)}`, { credentials: "same-origin", cache: "no-store" });
        const status = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(status.detail || "작업 조회 실패");
        if (status.status === "failed") {
          forgetRememberedLrcJob(entry.id);
          // 앱 시작 때 과거 실패 경고를 다시 띄우지 않는다. 방금 실행한
          // 작업의 실패는 waitForLrcJob에서 행동 버튼과 함께 한 번만 표시한다.
          continue;
        }
        if (status.status !== "complete") {
          if (!monitoringLrcJobs.has(entry.id)) {
            monitoringLrcJobs.add(entry.id);
            updateRememberedLrcJob(entry.id, { status: status.status });
            waitForLrcJob(status, null)
              .then(() => recoverLrcJobs())
              .catch((error) => message(error.message, true))
              .finally(() => monitoringLrcJobs.delete(entry.id));
          }
          continue;
        }
        const result = await fetch(`/api/mp3-player/lrc-jobs/${encodeURIComponent(entry.id)}/result`, { credentials: "same-origin", cache: "no-store" });
        if (!result.ok) throw new Error("완성 LRC 조회 실패");
        text = await result.text();
        updateRememberedLrcJob(entry.id, { status: "complete", resultText: text });
      }
      const index = playlist.findIndex((item) => reviewTrackKey(item) === entry.key || item.title === entry.title);
      if (index < 0) {
        message(`${entry.title} LRC가 완성됐습니다. 해당 플레이리스트를 열면 자동 적용됩니다.`);
        continue;
      }
      const item = playlist[index];
      const filename = trackFilename(item) || `${item.title || "audio"}.mp3`;
      item.lrcFile = new File([text], filename.replace(/\.mp3$/i, ".lrc"), { type: "text/plain;charset=utf-8" });
      item.has_lrc = true;
      if (index === playlistIndex) await applyLrc(item.lrcFile, item.file || null);
      saveActiveLrcJobs(getActiveLrcJobs().filter((jobEntry) => jobEntry.id !== entry.id));
      message(`${entry.title}의 완성된 LRC를 복구해 적용했습니다.`);
    } catch (_) {
      // 네트워크가 잠시 끊긴 경우 작업 번호를 보존하고 다음 접속에서 다시 확인한다.
    }
  }
}

function requestGeneratedLrc(form, file) {
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    const startedAt = Date.now();
    let elapsedTimer = null;
    request.open("POST", "/api/mp3-player/lrc-jobs");
    request.withCredentials = true;
    request.upload.addEventListener("progress", (event) => {
      if (!event.lengthComputable) return;
      const uploadPercent = Math.round(event.loaded / event.total * 100);
      showLrcProgress("1/3 · MP3 전송 중", `${uploadPercent}%`, Math.max(2, Math.round(uploadPercent * 0.25)));
    });
    request.upload.addEventListener("load", () => {
      showLrcProgress("2/3 · 언어 감지·가사 분석 중", "경과 0:00", 25, true);
      elapsedTimer = setInterval(() => {
        const elapsed = Math.floor((Date.now() - startedAt) / 1000);
        $("lrc-progress-detail").textContent = `경과 ${clock(elapsed)}`;
      }, 1000);
    });
    request.addEventListener("load", () => {
      clearInterval(elapsedTimer);
      if (request.status >= 200 && request.status < 300) {
        try { resolve(JSON.parse(request.responseText)); }
        catch (_) { reject(new Error("LRC 작업 번호를 받지 못했습니다")); }
      }
      else {
        let detail = `HTTP ${request.status}`;
        try { detail = JSON.parse(request.responseText).detail || detail; } catch (_) {}
        reject(new Error(detail));
      }
    });
    request.addEventListener("error", () => { clearInterval(elapsedTimer); reject(new Error("LRC 생성 서버에 연결하지 못했습니다")); });
    request.addEventListener("abort", () => { clearInterval(elapsedTimer); reject(new Error("LRC 생성을 취소했습니다")); });
    showLrcProgress("1/3 · MP3 전송 준비", "0%", 2);
    request.send(form);
  });
}

function sendLrcChunk(file, uploadId, index, total, chunkSize, startedAt) {
  return new Promise((resolve, reject) => {
    const start = index * chunkSize;
    const blob = file.slice(start, Math.min(file.size, start + chunkSize));
    const form = new FormData();
    form.append("upload_id", uploadId);
    form.append("index", String(index));
    form.append("total", String(total));
    form.append("filename", file.name);
    form.append("chunk", blob, `${file.name}.part${index}`);
    const request = new XMLHttpRequest();
    let elapsedTimer = null;
    request.open("POST", "/api/mp3-player/lrc-jobs/chunk");
    request.withCredentials = true;
    request.upload.addEventListener("progress", (event) => {
      if (!event.lengthComputable) return;
      const sent = start + event.loaded;
      const uploadPercent = Math.min(100, Math.round(sent / file.size * 100));
      showLrcProgress(`1/3 · MP3 분할 전송 ${index + 1}/${total}`, `${uploadPercent}%`, Math.max(2, Math.round(uploadPercent * 0.25)));
    });
    request.upload.addEventListener("load", () => {
      if (index !== total - 1) return;
      showLrcProgress("2/3 · 조각 결합·가사 분석 중", "경과 0:00", 25, true);
      elapsedTimer = setInterval(() => {
        const elapsed = Math.floor((Date.now() - startedAt) / 1000);
        $("lrc-progress-detail").textContent = `경과 ${clock(elapsed)}`;
      }, 1000);
    });
    request.addEventListener("load", () => {
      clearInterval(elapsedTimer);
      if (request.status >= 200 && request.status < 300) resolve(request.responseText);
      else {
        let detail = `HTTP ${request.status}`;
        try { detail = JSON.parse(request.responseText).detail || detail; } catch (_) {}
        reject(new Error(detail));
      }
    });
    request.addEventListener("error", () => { clearInterval(elapsedTimer); reject(new Error("MP3 조각 전송에 실패했습니다")); });
    request.send(form);
  });
}

async function requestChunkedGeneratedLrc(file) {
  const chunkSize = 16 * 1024 * 1024;
  const total = Math.ceil(file.size / chunkSize);
  const uploadId = crypto.randomUUID ? crypto.randomUUID() : "10000000-1000-4000-8000-100000000000".replace(/[018]/g, (character) => (character ^ crypto.getRandomValues(new Uint8Array(1))[0] & 15 >> character / 4).toString(16));
  const startedAt = Date.now();
  let responseText = "";
  for (let index = 0; index < total; index += 1) {
    responseText = await sendLrcChunk(file, uploadId, index, total, chunkSize, startedAt);
  }
  let job;
  try { job = JSON.parse(responseText); } catch (_) { throw new Error("LRC 작업 번호를 받지 못했습니다"); }
  if (!job?.id) throw new Error("LRC 작업 번호를 받지 못했습니다");
  return job;
}

async function submitLrcJob(track) {
  const file = track instanceof File ? track : track?.file;
  const macMatch = await findMatchingMacLibraryTrack(track);
  let macLibraryError = null;
  if (macMatch) {
    try {
      return await requestMacLibraryLrcJob(macMatch, track);
    } catch (error) {
      // 보관함이 요청 사이에 변경되었으면 로컬 파일이 있을 때만 업로드 방식으로 되돌아간다.
      macLibraryError = error;
      macLibraryMatchPromise = null;
    }
  }
  if (!file) {
    throw macLibraryError || new Error("Mac 좋아요플레이에서 같은 곡을 찾지 못했습니다. 보관함을 새로고침해 주세요.");
  }
  const form = new FormData();
  form.append("file", file, file.name);
  const job = file.size > 80 * 1024 * 1024
    ? await requestChunkedGeneratedLrc(file)
    : await requestGeneratedLrc(form, file);
  rememberLrcJob(job, file);
  return job;
}

async function requestMacLibraryLrcJob(macTrack, track) {
  const filename = trackFilename(track) || macTrack.name;
  const size = trackFileSize(track);
  const libraryKind = macTrack.library_kind || trackLibraryKind(macTrack);
  showLrcProgress("1/3 · Mac 원본 확인", `${libraryKind === "favorites" ? "좋아요플레이" : "Mac 보관함"} · MP3 전송 생략`, 8);
  const response = await fetch("/api/mp3-player/lrc-jobs/from-library", {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      file_id: macTrack.id,
      expected_name: filename,
      expected_size: size,
      library_kind: libraryKind,
    }),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
  showLrcProgress("2/3 · Mac 원본으로 가사 분석 중", "업로드 0MB", 10, true);
  rememberLrcJob(data, track);
  return data;
}

function trackFilename(track) {
  if (track instanceof File) return track.name || "";
  return track?.file?.name || track?.name || (track?.title ? `${track.title}.mp3` : "");
}

function trackFileSize(track) {
  if (track instanceof File) return Number(track.size || 0);
  return Number(track?.file?.size || track?.size || 0);
}

function trackLibraryKind(track) {
  if (track?.library_kind) return track.library_kind;
  return String(track?.stream_url || "").includes("favorites-library") ? "favorites" : "library";
}

function trackYoutubeId(track) {
  const match = trackFilename(track).match(/\[([A-Za-z0-9_-]{11})\](?:\.mp3)?$/i);
  return match?.[1] || "";
}

function normalizedTrackName(value) {
  return String(value || "").normalize("NFC").toLocaleLowerCase();
}

async function findMatchingMacLibraryTrack(file) {
  const filename = trackFilename(file);
  const size = trackFileSize(file);
  if (!filename) return null;
  if (!macLibraryMatchPromise) {
    macLibraryMatchPromise = Promise.all([
      ["favorites", "/api/mp3-player/favorites-library"],
      ["library", "/api/mp3-player/library"],
    ].map(async ([libraryKind, url]) => {
      const response = await fetch(url, { credentials: "same-origin", cache: "no-store" });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) return [];
      return (data.items || []).map((item) => ({ ...item, library_kind: libraryKind }));
    })).then((groups) => groups.flat()).catch(() => []);
  }
  const items = await macLibraryMatchPromise;
  const name = normalizedTrackName(filename);
  const youtubeId = trackYoutubeId(file);
  return items.find((item) => (
    normalizedTrackName(item.name) === name && (!size || Number(item.size) === size)
  )) || (youtubeId ? items.find((item) => trackYoutubeId(item) === youtubeId) : null) || null;
}

function parseLrc(text) {
  const offsetMatch = text.match(/^\[offset:([+-]?\d+)\]/im);
  const offset = offsetMatch ? Number(offsetMatch[1]) / 1000 : 0;
  const rows = [];
  for (const raw of text.split(/\r?\n/)) {
    const stamps = [...raw.matchAll(/\[(\d{1,3}):(\d{2})(?:[.:](\d{1,3}))?\]/g)];
    const content = raw.replace(/\[[^\]]+\]/g, "").trim();
    if (!content) continue;
    for (const stamp of stamps) {
      const fraction = stamp[3] ? Number(`0.${stamp[3].padEnd(3, "0").slice(0, 3)}`) : 0;
      rows.push({ time: Math.max(0, Number(stamp[1]) * 60 + Number(stamp[2]) + fraction + offset), text: content });
    }
  }
  return rows.sort((a, b) => a.time - b.time);
}

function renderLyrics() {
  const root = $("lyrics");
  root.replaceChildren();
  activeLyric = -1;
  if (!lyricRows.length) {
    const empty = document.createElement("p");
    empty.className = "lyrics-empty";
    empty.textContent = "시간 정보가 있는 가사를 찾지 못했어요.";
    root.append(empty);
    updateLyricsStudyButton();
    return;
  }
  lyricRows.forEach((row, index) => {
    const button = document.createElement("button");
    const text = document.createElement("span");
    button.type = "button";
    button.className = "lyric-line";
    button.dataset.index = index;
    text.textContent = row.text;
    button.append(text);
    button.addEventListener("click", () => {
      if (Date.now() < suppressLyricClickUntil) return;
      audio.currentTime = row.time;
      audio.play().catch(() => {});
      syncLyrics(true);
    });
    root.append(button);
  });
  $("lyrics-state").textContent = `${lyricRows.length}줄 · 동기화됨`;
  $("lyrics-toggle").disabled = false;
  updateLyricsStudyButton();
  fitVisibleLyrics();
}

function fitVisibleLyrics() {
  cancelAnimationFrame(lyricFitFrame);
  lyricFitFrame = requestAnimationFrame(() => {
    const root = $("lyrics");
    const nodes = [...root.querySelectorAll(".lyric-line.nearby")];
    nodes.forEach((node) => {
      node.style.removeProperty("font-size");
      node.style.removeProperty("overflow-y");
    });
    lyricFitFrame = requestAnimationFrame(() => {
      const landscape = matchMedia("(orientation: landscape) and (max-height: 560px)").matches;
      nodes.forEach((node) => {
        if (node.classList.contains("before")) return;
        const span = node.querySelector("span");
        if (!span || node.clientHeight <= 0 || node.clientWidth <= 0) return;
        let size = Number.parseFloat(getComputedStyle(node).fontSize) || 16;
        const minimum = node.classList.contains("active") ? (landscape ? 22 : 18) : (landscape ? 17 : 14);
        while (size > minimum && (span.scrollHeight > node.clientHeight + 1 || span.scrollWidth > node.clientWidth + 1)) {
          size -= 1;
          node.style.fontSize = `${size}px`;
        }
        if (span.scrollHeight > node.clientHeight + 1) node.style.overflowY = "auto";
      });
    });
  });
}

function syncLyrics(force = false) {
  if (!lyricRows.length) return;
  let next = -1;
  for (let index = 0; index < lyricRows.length; index += 1) {
    if (lyricRows[index].time <= audio.currentTime + 0.08) next = index;
    else break;
  }
  if (!force && next === activeLyric && $("lyrics").querySelector(".nearby")) return;
  $("lyrics").querySelectorAll(".lyric-line").forEach((node) => node.classList.remove("active", "nearby", "before", "after"));
  activeLyric = next;
  if (next < 0) {
    [0, 1, 2].forEach((index) => $("lyrics").querySelector(`[data-index="${index}"]`)?.classList.add("nearby", index === 0 ? "active" : "after"));
    fitVisibleLyrics();
    return;
  }
  const previous = $("lyrics").querySelector(`[data-index="${next - 1}"]`);
  const node = $("lyrics").querySelector(`[data-index="${next}"]`);
  const following = $("lyrics").querySelector(`[data-index="${next + 1}"]`);
  previous?.classList.add("nearby", "before");
  node?.classList.add("active");
  node?.classList.add("nearby");
  if (node) {
    const length = Array.from(lyricRows[next]?.text || "").length;
    node.classList.toggle("long", length > 18);
    node.classList.toggle("very-long", length > 28);
  }
  following?.classList.add("nearby", "after");
  fitVisibleLyrics();
}

function fileStem(file) {
  return (file.webkitRelativePath || file.name).replace(/\.[^.]+$/, "").toLocaleLowerCase();
}

function makePlaylistItems(files) {
  const allFiles = Array.from(files || []);
  const lrcByPath = new Map();
  const lrcByName = new Map();
  allFiles.filter((file) => /\.lrc$/i.test(file.name)).forEach((file) => {
    lrcByPath.set(fileStem(file), file);
    const stem = file.name.replace(/\.lrc$/i, "").toLocaleLowerCase();
    if (!lrcByName.has(stem)) lrcByName.set(stem, file);
  });
  return allFiles
    .filter((file) => /\.mp3$/i.test(file.name) || file.type === "audio/mpeg")
    .sort((left, right) => filenameSorter.compare(left.webkitRelativePath || left.name, right.webkitRelativePath || right.name))
    .map((file) => ({
      file,
      lrcFile: lrcByPath.get(fileStem(file)) || lrcByName.get(file.name.replace(/\.mp3$/i, "").toLocaleLowerCase()) || null,
      title: file.name.replace(/\.mp3$/i, ""),
    }));
}

function playlistFolderName(files) {
  const first = Array.from(files || []).find((file) => file.webkitRelativePath);
  return first?.webkitRelativePath?.split("/")[0] || "최근 플레이리스트";
}

function saveRecentPlaylist(files, count) {
  if (!count) return;
  const name = playlistFolderName(files);
  const previous = getRecentPlaylist();
  const samePlaylist = previous?.name === name && Number(previous?.count) === count;
  const recent = {
    name,
    count,
    savedAt: Date.now(),
    lastIndex: samePlaylist ? Number(previous.lastIndex || 0) : 0,
    lastTime: samePlaylist ? Number(previous.lastTime || 0) : 0,
    lastTitle: samePlaylist ? String(previous.lastTitle || "") : "",
  };
  try { localStorage.setItem(RECENT_PLAYLIST_KEY, JSON.stringify(recent)); } catch (_) {}
  showRecentPlaylistShortcut();
}

function savePlaybackPosition(force = false) {
  const now = Date.now();
  if (!force && now - lastPlaybackSaveAt < 4000) return;
  lastPlaybackSaveAt = now;
  savePlaybackSession(now);
  if (!activePlaylistName || playlistIndex < 0 || !playlist[playlistIndex]) return;
  const recent = getRecentPlaylist();
  if (!recent || recent.name !== activePlaylistName || Number(recent.count) !== playlist.length) return;
  recent.lastIndex = playlistIndex;
  recent.lastTime = Math.max(0, Math.floor(audio.currentTime || 0));
  recent.lastTitle = playlist[playlistIndex].title;
  recent.savedAt = now;
  try { localStorage.setItem(RECENT_PLAYLIST_KEY, JSON.stringify(recent)); } catch (_) {}
  savePlaylistProgress(activePlaylistName, playlist.length, {
    lastIndex: playlistIndex,
    lastTime: recent.lastTime,
    lastTitle: recent.lastTitle,
  });
}

function getPlaybackSession() {
  try { return JSON.parse(localStorage.getItem(PLAYBACK_SESSION_KEY) || "null"); }
  catch (_) { return null; }
}

function shuffleTrackKey(item) {
  if (!item) return "";
  if (item.id) return `mac:${item.id}`;
  const file = item.file;
  return `device:${file?.webkitRelativePath || file?.name || item.name || item.title || ""}:${Number(file?.size || 0)}:${Number(file?.lastModified || 0)}`;
}

function recordShuffleTrack(index) {
  if (!shufflePlaylist || index < 0 || index >= playlist.length) return;
  const key = shuffleTrackKey(playlist[index]);
  if (!key || shuffleHistory[shuffleHistoryCursor] === key) return;
  shuffleHistory = shuffleHistory.slice(0, shuffleHistoryCursor + 1);
  shuffleHistory.push(key);
  shuffleHistoryCursor = shuffleHistory.length - 1;
}

function restoreShuffleHistory(state) {
  const saved = Array.isArray(state?.shuffleHistory) ? state.shuffleHistory.filter((key) => typeof key === "string") : [];
  const known = new Set(playlist.map(shuffleTrackKey));
  shuffleHistory = saved.filter((key) => known.has(key)).slice(-300);
  shuffleHistoryCursor = Math.min(Number(state?.shuffleHistoryCursor ?? shuffleHistory.length - 1), shuffleHistory.length - 1);
  if (shuffleHistoryCursor < -1) shuffleHistoryCursor = -1;
}

function savePlaybackSession(savedAt = Date.now()) {
  const localItem = playlistIndex >= 0 ? playlist[playlistIndex] : null;
  const item = localItem || remoteTrack;
  if (!item) return;
  const state = {
    version: 2,
    source: remoteTrack ? "mac" : "device",
    playlistName: activePlaylistName || "",
    playlistCount: playlist.length,
    index: playlistIndex,
    title: item.title || item.file?.name?.replace(/\.mp3$/i, "") || "",
    fileName: item.name || item.file?.name || "",
    remoteId: remoteTrack?.id || "",
    time: Math.max(0, Number(audio.currentTime || 0)),
    wasPlaying: !audio.paused && !audio.ended,
    shuffle: shufflePlaylist,
    shuffleHistory: shuffleHistory.slice(-300),
    shuffleHistoryCursor: Math.max(-1, shuffleHistoryCursor - Math.max(0, shuffleHistory.length - 300)),
    repeat: repeatMode,
    filter: playlistViewMode,
    favoritesOnly,
    rate: Number(audio.playbackRate || 1),
    lyricSize: $("lyric-size").dataset.size || "xlarge",
    lyricsCollapsed: $("lyrics-card").classList.contains("collapsed"),
    followLyrics,
    hadLrc: Boolean(currentLrc),
    savedAt,
  };
  try { localStorage.setItem(PLAYBACK_SESSION_KEY, JSON.stringify(state)); } catch (_) {}
}

function renderRestoreHint(state = getPlaybackSession()) {
  const hint = $("restore-hint");
  if (!hint) return;
  if (!state?.title) { hint.classList.add("hidden"); return; }
  const position = clock(Number(state.time || 0));
  hint.classList.remove("hidden");
  $("restore-hint-title").textContent = state.source === "mac"
    ? `최근 재생 복구 중 · ${state.title}`
    : `최근 곡 · ${state.title}`;
  $("restore-hint-copy").textContent = state.source === "mac"
    ? `${position} 위치를 불러오고 있습니다.`
    : `같은 폴더를 다시 선택하면 ${position} 위치부터 바로 이어집니다.`;
}

function getRecentPlaylist() {
  try { return JSON.parse(localStorage.getItem(RECENT_PLAYLIST_KEY) || "null"); } catch (_) { return null; }
}

function playlistProgressId(name, count) {
  return `${name}\u0000${count}`;
}

function getPlaylistProgress(name, count) {
  try {
    const all = JSON.parse(localStorage.getItem(PLAYLIST_PROGRESS_KEY) || "{}");
    return all[playlistProgressId(name, count)] || null;
  } catch (_) { return null; }
}

function savePlaylistProgress(name, count, progress) {
  try {
    const all = JSON.parse(localStorage.getItem(PLAYLIST_PROGRESS_KEY) || "{}");
    all[playlistProgressId(name, count)] = { ...progress, savedAt: Date.now() };
    const newest = Object.entries(all)
      .sort((left, right) => Number(right[1]?.savedAt || 0) - Number(left[1]?.savedAt || 0))
      .slice(0, 30);
    localStorage.setItem(PLAYLIST_PROGRESS_KEY, JSON.stringify(Object.fromEntries(newest)));
  } catch (_) {}
}

function showRecentPlaylistShortcut() {
  const recent = getRecentPlaylist();
  const button = $("recent-playlist");
  if (!recent?.name || !Number(recent.count)) { button.classList.add("hidden"); return; }
  button.textContent = `♫ ${recent.name} · ${recent.count}곡 다시 열기`;
  button.classList.remove("hidden");
}

function playlistEligibleEntries() {
  let entries = playlist.map((item, index) => ({ item, index }));
  if (favoritesOnly) entries = entries.filter(({ item }) => isFavorite(item));
  if (playlistViewMode === "lrc-none") entries = entries.filter(({ item }) => !item.lrcFile);
  if (playlistViewMode === "lrc-only") entries = entries.filter(({ item }) => Boolean(item.lrcFile));
  if (playlistViewMode.startsWith("lang-")) {
    const language = playlistViewMode.slice(5);
    entries = entries.filter(({ item }) => item.lyricsLanguage === language);
  }
  if (playlistViewMode === "size-asc") entries.sort((left, right) => Number(left.item.file?.size || left.item.size || 0) - Number(right.item.file?.size || right.item.size || 0));
  if (playlistViewMode === "duration-asc") entries.sort((left, right) =>
    Number(left.item.duration || Infinity) - Number(right.item.duration || Infinity));
  return entries;
}

function readAudioDuration(item) {
  if (Number.isFinite(item.duration) && item.duration > 0) return Promise.resolve(item.duration);
  if (!item.file) return Promise.resolve(Infinity);
  return new Promise((resolve) => {
    const probe = document.createElement("audio");
    const url = URL.createObjectURL(item.file);
    const finish = (duration = Infinity) => {
      item.duration = Number.isFinite(duration) && duration > 0 ? duration : Infinity;
      probe.removeAttribute("src"); URL.revokeObjectURL(url); resolve(item.duration);
    };
    probe.preload = "metadata";
    probe.addEventListener("loadedmetadata", () => finish(probe.duration), { once: true });
    probe.addEventListener("error", () => finish(), { once: true });
    probe.src = url;
  });
}

async function preparePlaylistFilter(mode) {
  if (mode === "duration-asc") {
    const pending = playlist.filter((item) => item.duration == null);
    for (let start = 0; start < pending.length; start += 6) {
      $("playlist-count").textContent = `재생시간 확인 ${Math.min(start + 6, pending.length)}/${pending.length}`;
      await Promise.all(pending.slice(start, start + 6).map(readAudioDuration));
    }
  }
  if (mode.startsWith("lang-")) {
    const pending = playlist.filter((item) => item.lrcFile && !item.lyricsLanguage);
    for (let start = 0; start < pending.length; start += 24) {
      $("playlist-count").textContent = `가사 언어 확인 ${Math.min(start + 24, pending.length)}/${pending.length}`;
      await Promise.all(pending.slice(start, start + 24).map(async (item) => {
        try {
          const resolved = resolveTrackLyricsLanguage(item, await item.lrcFile.text());
          item.lyricsLanguage = resolved.language;
          item.lrcLanguageMismatch = resolved.mismatch;
        }
        catch (_) { item.lyricsLanguage = "unknown"; }
      }));
    }
  }
}

function renderPlaylist() {
  $("playlist").classList.toggle("hidden", playlist.length < 2);
  const favoriteKeys = new Set(getFavorites().map((entry) => entry.key));
  const visibleEntries = playlistEligibleEntries();
  const currentPosition = visibleEntries.findIndex(({ index }) => index === playlistIndex);
  $("playlist-count").textContent = `${visibleEntries.length}/${playlist.length}곡${currentPosition >= 0 ? ` · 필터 내 ${currentPosition + 1}번째` : ""}`;
  const list = $("playlist-list");
  list.replaceChildren();
  if ($("playlist-body").classList.contains("hidden")) return;
  if (!visibleEntries.length) {
    const empty = document.createElement("li");
    empty.className = "favorites-empty"; empty.textContent = favoritesOnly ? "조건에 맞는 즐겨찾기 곡이 없습니다." : "선택한 조건에 맞는 곡이 없습니다.";
    list.append(empty); return;
  }
  visibleEntries.forEach(({ item, index }, visibleIndex) => {
    const favorite = favoriteKeys.has(favoriteIdentity(item));
    const row = document.createElement("li");
    const number = document.createElement("span");
    const playButton = document.createElement("button");
    const title = document.createElement("span");
    const remove = document.createElement("button");
    row.className = `playlist-item${index === playlistIndex ? " current" : ""}${favorite ? " favorite" : ""}`;
    number.className = "playlist-index"; number.textContent = String(visibleIndex + 1);
    playButton.type = "button"; playButton.className = "playlist-play"; playButton.setAttribute("aria-label", `${item.title} 재생`);
    title.textContent = item.title; playButton.append(title);
    playButton.addEventListener("click", () => loadPlaylistTrack(index, true));
    remove.type = "button"; remove.className = "playlist-remove"; remove.textContent = "×"; remove.setAttribute("aria-label", `${item.title} 목록에서 삭제`);
    remove.addEventListener("click", () => removePlaylistTrack(index));
    row.append(number, playButton, remove); list.append(row);
  });
}

function favoriteIdentity(item) {
  const name = item?.file?.name || item?.name || item?.title || "";
  return String(name).normalize("NFC").trim().toLocaleLowerCase();
}

function getFavorites() {
  return syncedFavorites;
}

function localFavorites() {
  try {
    const parsed = JSON.parse(localStorage.getItem(FAVORITES_KEY) || "[]");
    return Array.isArray(parsed) ? parsed : [];
  } catch (_) { return []; }
}

function saveFavoriteCache() {
  try { localStorage.setItem(FAVORITES_KEY, JSON.stringify(syncedFavorites.slice(-1000))); } catch (_) {}
}

async function loadSyncedFavorites() {
  const local = localFavorites();
  try {
    const response = await fetch("/api/me/mp3-favorites", { credentials: "same-origin", cache: "no-store" });
    const server = await response.json().catch(() => []);
    if (!response.ok) throw new Error("좋아요 동기화 실패");
    const merged = new Map((Array.isArray(server) ? server : []).map((entry) => [entry.key, entry]));
    for (const entry of local) {
      const key = String(entry.key || "").split("/").at(-1)?.normalize("NFC").toLocaleLowerCase();
      if (!key || merged.has(key)) continue;
      const migrated = { ...entry, key };
      merged.set(key, migrated);
      await fetch("/api/me/mp3-favorites", {
        method: "PUT",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ track_key: key, title: entry.title || "", playlist: entry.playlist || "" }),
      });
    }
    syncedFavorites = [...merged.values()];
    saveFavoriteCache();
    updateFavoriteButton();
    renderPlaylist();
  } catch (_) {
    syncedFavorites = local.map((entry) => ({
      ...entry,
      key: String(entry.key || "").split("/").at(-1)?.normalize("NFC").toLocaleLowerCase(),
    })).filter((entry) => entry.key);
  }
}

function isFavorite(item) {
  const key = favoriteIdentity(item);
  return Boolean(key && getFavorites().some((entry) => entry.key === key));
}

function updateFavoriteButton() {
  const item = playlistIndex >= 0 ? playlist[playlistIndex] : remoteTrack;
  const favorite = item ? isFavorite(item) : false;
  $("favorite-track").disabled = !item;
  $("favorite-track").setAttribute("aria-pressed", String(favorite));
  $("favorite-track").setAttribute("aria-label", favorite ? "현재 곡 좋아요 취소" : "현재 곡 좋아요");
}

async function toggleCurrentFavorite() {
  const item = playlistIndex >= 0 ? playlist[playlistIndex] : remoteTrack;
  if (!item) return;
  const key = favoriteIdentity(item);
  let favorites = getFavorites();
  const exists = favorites.some((entry) => entry.key === key);
  favorites = favorites.filter((entry) => entry.key !== key);
  if (!exists) favorites.push({ key, title: item.title, playlist: activePlaylistName, savedAt: Date.now() });
  syncedFavorites = favorites.slice(-1000);
  saveFavoriteCache();
  try {
    let response;
    if (exists) {
      response = await fetch(`/api/me/mp3-favorites?track_key=${encodeURIComponent(key)}`, {
        method: "DELETE", credentials: "same-origin",
      });
    } else {
      response = await fetch("/api/me/mp3-favorites", {
        method: "PUT",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ track_key: key, title: item.title || "", playlist: activePlaylistName }),
      });
    }
    if (!response.ok) throw new Error("좋아요 동기화 실패");
  } catch (_) {
    message("이 기기에는 반영했지만 서버 동기화는 다음 접속 때 다시 시도합니다.", true);
  }
  updateFavoriteButton(); renderPlaylist();
  message(exists ? "좋아요를 취소했습니다." : "즐겨찾기에 저장했습니다.");
}

function reviewTrackKey(item) {
  if (item?.file) return item.file.webkitRelativePath || item.file.name;
  if (item?.id) return `mac:${item.id}`;
  return item ? `track:${favoriteIdentity(item)}` : "";
}

function currentReviewTrack() {
  return playlistIndex >= 0 ? playlist[playlistIndex] : remoteTrack;
}

function getLrcReviewQueue() {
  try {
    const parsed = JSON.parse(localStorage.getItem(LRC_REVIEW_QUEUE_KEY) || "[]");
    return Array.isArray(parsed) ? parsed : [];
  } catch (_) { return []; }
}

function saveLrcReviewQueue(queue) {
  try { localStorage.setItem(LRC_REVIEW_QUEUE_KEY, JSON.stringify(queue)); } catch (_) {}
  renderLrcReviewQueue();
}

function renderLrcReviewQueue() {
  const queue = getLrcReviewQueue();
  const list = $("lrc-review-list");
  list.replaceChildren();
  queue.forEach((entry) => {
    const row = document.createElement("li");
    row.textContent = entry.title;
    list.append(row);
  });
  const item = currentReviewTrack();
  const key = reviewTrackKey(item);
  $("lrc-review-check").disabled = !key || reviewRunning;
  $("lrc-review-check").checked = Boolean(key && queue.some((entry) => entry.key === key));
  const landscapeReview = $("landscape-review");
  const requested = Boolean(key && queue.some((entry) => entry.key === key));
  landscapeReview.disabled = !key || reviewRunning;
  landscapeReview.setAttribute("aria-pressed", String(requested));
  landscapeReview.setAttribute("aria-label", requested ? "현재 곡 LRC 검토 목록에서 제거" : "현재 곡 LRC 검토 목록에 추가");
  landscapeReview.title = requested ? "LRC 검토 요청됨" : "LRC 검토 요청";
  $("lrc-review-start").disabled = !queue.length || reviewRunning;
  $("lrc-review-start").textContent = reviewRunning ? "검토 진행 중…" : `검토 시작${queue.length ? ` · ${queue.length}곡` : ""}`;
}

function setCurrentLrcReviewRequested(requested) {
  const item = currentReviewTrack();
  const key = reviewTrackKey(item);
  if (!key || reviewRunning) return;
  const landscapeReview = $("landscape-review");
  landscapeReview.setAttribute("aria-pressed", String(requested));
  landscapeReview.setAttribute("aria-label", requested ? "현재 곡 LRC 검토 목록에서 제거" : "현재 곡 LRC 검토 목록에 추가");
  landscapeReview.title = requested ? "LRC 검토 요청됨" : "LRC 검토 요청";
  $("lrc-review-check").checked = requested;
  const queue = getLrcReviewQueue().filter((entry) => entry.key !== key);
  if (requested) {
    queue.push({
      key,
      title: item.title,
      playlist: activePlaylistName,
      remoteId: item.id || "",
      requestedAt: Date.now(),
    });
    message("이 곡을 LRC 검토 목록에 넣었습니다.");
  } else message("이 곡을 LRC 검토 목록에서 뺐습니다.");
  saveLrcReviewQueue(queue);
}

function setPlaylist(files, append = false) {
  const items = makePlaylistItems(files);
  if (!items.length) { message("선택한 곳에서 MP3 파일을 찾지 못했습니다.", true); return; }
  const folderName = playlistFolderName(files);
  const session = getPlaybackSession();
  const savedProgress = !append ? getPlaylistProgress(folderName, items.length) : null;
  const sessionMatches = !append && session?.source === "device"
    && session.playlistName === folderName
    && Number(session.playlistCount) === items.length;
  const progress = savedProgress || (sessionMatches ? {
    lastIndex: session.index,
    lastTime: session.time,
    lastTitle: session.title,
  } : null);
  const canResume = Number(progress?.lastIndex) >= 0
    && Number(progress?.lastIndex) < items.length
    && (Number(progress?.lastIndex) > 0 || Number(progress?.lastTime) > 3);
  const wasEmpty = !playlist.length;
  playlist = append ? playlist.concat(items) : items;
  if (!append) activePlaylistName = folderName;
  if (!append) {
    if (sessionMatches && session?.shuffle) restoreShuffleHistory(session);
    else { shuffleHistory = []; shuffleHistoryCursor = -1; }
  }
  if (!append) saveRecentPlaylist(files, items.length);
  if (!append || wasEmpty) {
    let startIndex = 0;
    let autoplay = false;
    pendingResumeTime = 0;
    if (canResume) {
      const titleIndex = items.findIndex((item) => item.title === progress.lastTitle);
      startIndex = titleIndex >= 0 ? titleIndex : Number(progress.lastIndex);
      pendingResumeTime = Number(progress.lastTime || 0);
      autoplay = true;
    }
    loadPlaylistTrack(startIndex, autoplay);
  }
  else renderPlaylist();
  renderLrcReviewQueue();
  recoverLrcJobs();
  void hydratePlaylistLrcFromMacLibrary(items);
  if (playlistViewMode !== "all") {
    void preparePlaylistFilter(playlistViewMode).then(() => {
      renderPlaylist();
      const eligible = playlistEligibleEntries();
      if (eligible.length && !eligible.some(({ index }) => index === playlistIndex)) loadPlaylistTrack(eligible[0].index, false);
    });
  }
  message(`${items.length}곡을 ${append ? "플레이리스트에 추가" : "불러왔"}습니다.`);
  $("restore-hint")?.classList.add("hidden");
  void syncFavoritesPlaylist();
}

async function hydratePlaylistLrcFromMacLibrary(items) {
  const pending = items.filter((item) => !item.lrcFile);
  if (!pending.length) return;
  try {
    const [libraryResponse, syncedResponse] = await Promise.all([
      fetch("/api/mp3-player/library", { credentials: "same-origin", cache: "no-store" }),
      fetch("/api/me/mp3-lrc-index", { credentials: "same-origin", cache: "no-store" }),
    ]);
    const data = await libraryResponse.json().catch(() => ({}));
    const synced = await syncedResponse.json().catch(() => []);
    const byName = new Map((data.items || []).map((entry) => [
      String(entry.name || "").normalize("NFC").toLocaleLowerCase(),
      entry,
    ]));
    const syncedKeys = new Set((Array.isArray(synced) ? synced : []).map((entry) => entry.key));
    await Promise.all(pending.map(async (item) => {
      const entry = byName.get(item.file.name.normalize("NFC").toLocaleLowerCase());
      const key = favoriteIdentity(item);
      const lrcUrl = entry?.lrc_url || (syncedKeys.has(key)
        ? `/api/me/mp3-lrc?track_key=${encodeURIComponent(key)}`
        : "");
      if (!lrcUrl) return;
      const lrcResponse = await fetch(lrcUrl, { credentials: "same-origin", cache: "no-store" });
      if (!lrcResponse.ok) return;
      const text = await lrcResponse.text();
      item.lrcFile = new File(
        [text],
        item.file.name.replace(/\.mp3$/i, ".lrc"),
        { type: "text/plain;charset=utf-8" },
      );
      if (playlist[playlistIndex] === item) await applyLrc(item.lrcFile, item.file);
    }));
    renderPlaylist();
  } catch (_) {
    // Mac 보관함을 사용할 수 없는 계정·네트워크에서는 기기 안의 LRC만 유지한다.
  }
}

function loadAudio(file, lrcFile = null) {
  if (!file || (!/\.mp3$/i.test(file.name) && file.type !== "audio/mpeg")) {
    message("MP3 파일을 선택해 주세요.", true); return;
  }
  if (audioUrl?.startsWith("blob:")) URL.revokeObjectURL(audioUrl);
  audioFile = file;
  remoteTrack = null;
  audioUrl = URL.createObjectURL(file);
  audio.src = audioUrl;
  lyricRows = []; currentLrc = ""; activeLyric = -1;
  updateGenerateButton();
  updateLyricsStudyButton();
  $("title").textContent = file.name.replace(/\.mp3$/i, "");
  setCurrentTrackTitle($("title").textContent);
  $("meta").textContent = `${(file.size / 1024 / 1024).toFixed(1)}MB · 기기에서 재생`;
  $("empty").classList.add("hidden");
  $("player").classList.remove("hidden");
  $("landscape-regenerate").disabled = false;
  $("download-lrc").classList.add("hidden");
  $("lyrics-toggle").disabled = true;
  $("lyrics-state").textContent = "가사를 불러오세요";
  $("lyrics").innerHTML = '<p class="lyrics-empty">같은 이름의 LRC가 있으면 자동으로 표시됩니다.<br>없다면 아래에서 LRC를 적용하거나 만들어 보세요.</p>';
  if ("mediaSession" in navigator) navigator.mediaSession.metadata = new MediaMetadata({ title: $("title").textContent, artist: "기기 MP3" });
  if (lrcFile) applyLrc(lrcFile, file);
  savePlaybackSession();
}

function loadPlaylistTrack(index, autoplay = false) {
  if (index < 0 || index >= playlist.length) return;
  if (!$("recommendations").classList.contains("hidden")) rememberRecommendationsReturn();
  playlistIndex = index;
  recordShuffleTrack(index);
  const item = playlist[index];
  if (item.stream_url) {
    loadRemoteAudio(item, autoplay, index).catch(() => message("좋아요음악 곡을 불러오지 못했습니다.", true));
    return;
  }
  loadAudio(item.file, item.lrcFile);
  renderPlaylist();
  renderLrcReviewQueue();
  updateFavoriteButton();
  if (autoplay) audio.play().catch(() => message("재생 버튼을 눌러 시작하세요."));
}

function adjacentPlaylistIndex(direction) {
  if (!playlist.length) return -1;
  const eligible = playlistEligibleEntries().map(({ index }) => index);
  if (!eligible.length) return -1;
  if (shufflePlaylist && eligible.length > 1) {
    recordShuffleTrack(playlistIndex);
    const byKey = new Map(eligible.map((index) => [shuffleTrackKey(playlist[index]), index]));
    if (direction < 0) {
      for (let cursor = shuffleHistoryCursor - 1; cursor >= 0; cursor -= 1) {
        const previous = byKey.get(shuffleHistory[cursor]);
        if (previous !== undefined) {
          shuffleHistoryCursor = cursor;
          savePlaybackSession();
          return previous;
        }
      }
      return -1;
    }
    for (let cursor = shuffleHistoryCursor + 1; cursor < shuffleHistory.length; cursor += 1) {
      const forward = byKey.get(shuffleHistory[cursor]);
      if (forward !== undefined) {
        shuffleHistoryCursor = cursor;
        savePlaybackSession();
        return forward;
      }
    }
    const candidates = eligible.filter((index) => index !== playlistIndex);
    const next = candidates[Math.floor(Math.random() * candidates.length)];
    shuffleHistory = shuffleHistory.slice(0, shuffleHistoryCursor + 1);
    shuffleHistory.push(shuffleTrackKey(playlist[next]));
    shuffleHistoryCursor = shuffleHistory.length - 1;
    savePlaybackSession();
    return next;
  }
  const position = eligible.indexOf(playlistIndex);
  if (position < 0) return eligible[0];
  const nextPosition = position + direction;
  if (nextPosition >= 0 && nextPosition < eligible.length) return eligible[nextPosition];
  return repeatMode === "all" ? (nextPosition < 0 ? eligible.at(-1) : eligible[0]) : -1;
}

function playAdjacent(direction) {
  const next = adjacentPlaylistIndex(direction);
  if (next >= 0) loadPlaylistTrack(next, true);
}

function isLandscapeLyricsMode() {
  return matchMedia("(orientation: landscape) and (max-height: 560px)").matches;
}

function beginLandscapeLyricsSwipe(event) {
  if (!isLandscapeLyricsMode() || !playlist.length) return;
  landscapeSwipe = { pointerId: event.pointerId, x: event.clientX, y: event.clientY };
  event.currentTarget.setPointerCapture?.(event.pointerId);
}

function finishLandscapeLyricsSwipe(event) {
  if (!landscapeSwipe || event.pointerId !== landscapeSwipe.pointerId) return;
  const dx = event.clientX - landscapeSwipe.x;
  const dy = event.clientY - landscapeSwipe.y;
  landscapeSwipe = null;
  if (Math.abs(dx) < 64 || Math.abs(dx) < Math.abs(dy) * 1.25) return;
  suppressLyricClickUntil = Date.now() + 500;
  playAdjacent(dx < 0 ? 1 : -1);
  message(dx < 0 ? "다음 곡을 재생합니다" : "이전 곡을 재생합니다");
}

function savePlaybackMode() {
  try { localStorage.setItem(PLAYBACK_MODE_KEY, JSON.stringify({ shuffle: shufflePlaylist, repeat: repeatMode })); } catch (_) {}
}

function savedPlaybackMode() {
  try { return JSON.parse(localStorage.getItem(PLAYBACK_MODE_KEY) || "null") || {}; } catch (_) { return {}; }
}

function setShuffle(enabled, persist = true) {
  shufflePlaylist = enabled;
  if (enabled && playlistIndex >= 0 && !shuffleHistory.length) recordShuffleTrack(playlistIndex);
  $("playlist-shuffle").querySelector(".control-label").textContent = enabled ? "무작위 재생" : "순서대로";
  $("playlist-shuffle").setAttribute("aria-pressed", String(enabled));
  $("shuffle-main").querySelector(".control-label").textContent = enabled ? "랜덤 재생" : "순서대로";
  $("shuffle-main").setAttribute("aria-pressed", String(enabled));
  if (persist) { savePlaybackMode(); savePlaybackSession(); }
}

function setRepeatMode(mode, persist = true) {
  repeatMode = ["all", "one", "off"].includes(mode) ? mode : "all";
  $("playlist-repeat").dataset.mode = repeatMode;
  $("playlist-repeat").querySelector(".control-label").textContent = repeatMode === "all" ? "전체 반복" : repeatMode === "one" ? "한 곡 반복" : "반복 끔";
  if (persist) { savePlaybackMode(); savePlaybackSession(); }
}

function setLyricSize(size) {
  const selected = LYRIC_SIZES.includes(size) ? size : "normal";
  $("lyrics").dataset.size = selected;
  $("lyric-size").dataset.size = selected;
  $("lyric-size").textContent = `가사 크기 · ${LYRIC_SIZE_LABELS[selected]}`;
  localStorage.setItem(LYRIC_SIZE_KEY, selected);
  savePlaybackSession();
}

function setLyricsCollapsed(collapsed) {
  $("lyrics-card").classList.toggle("collapsed", collapsed);
  $("lyrics-toggle").textContent = collapsed ? "가사 펼치기" : "가사 접기";
  $("lyrics-toggle").setAttribute("aria-expanded", String(!collapsed));
  localStorage.setItem(LYRICS_COLLAPSED_KEY, collapsed ? "1" : "0");
  savePlaybackSession();
}

function removePlaylistTrack(index) {
  if (index < 0 || index >= playlist.length) return;
  const removingCurrent = index === playlistIndex;
  playlist.splice(index, 1);
  if (!playlist.length) {
    playlistIndex = -1; audio.pause(); audio.removeAttribute("src");
    $("player").classList.add("hidden"); $("empty").classList.remove("hidden");
    renderPlaylist(); return;
  }
  if (index < playlistIndex) playlistIndex -= 1;
  if (removingCurrent) loadPlaylistTrack(Math.min(index, playlist.length - 1), false);
  else renderPlaylist();
}

function preparePlayer(title, meta) {
  lyricRows = []; currentLrc = ""; activeLyric = -1;
  updateGenerateButton();
  updateLyricsStudyButton();
  $("title").textContent = title;
  setCurrentTrackTitle(title);
  $("meta").textContent = meta;
  $("empty").classList.add("hidden");
  $("player").classList.remove("hidden");
  $("landscape-regenerate").disabled = false;
  $("download-lrc").classList.add("hidden");
  $("lyrics-toggle").disabled = true;
  $("lyrics-state").textContent = "가사를 불러오세요";
  $("lyrics").innerHTML = '<p class="lyrics-empty">같은 이름의 LRC가 있으면 자동으로 표시됩니다.<br>없다면 아래에서 LRC를 적용하거나 만들어 보세요.</p>';
}

async function syncAutomaticLyrics(item, selectedRemoteId, attempt = 0) {
  if (!item?.id || remoteTrack?.id !== selectedRemoteId || !item.stream_url?.includes("favorites-library")) return;
  try {
    const response = await fetch(`/api/mp3-player/favorites-library/${encodeURIComponent(item.id)}/postprocess`, {
      credentials: "same-origin", cache: "no-store",
    });
    if (response.status === 404) return;
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || "자동 가사 상태를 읽지 못했습니다");
    if (data.has_lrc && !lyricRows.length) {
      const lrcResponse = await fetch(`/api/mp3-player/favorites-library/${encodeURIComponent(item.id)}/lrc`, {
        credentials: "same-origin", cache: "no-store",
      });
      if (lrcResponse.ok && remoteTrack?.id === selectedRemoteId) {
        await applyLrc(new File([await lrcResponse.text()], item.name.replace(/\.mp3$/i, ".lrc"), { type: "text/plain;charset=utf-8" }), null);
      }
    }
    const key = currentLyricsStudyKey(detectLyricsStudyTarget());
    if (key && data.source_message_id) {
      const complete = data.status === "complete" && data.result;
      const record = {
        status: complete ? "complete" : data.status === "failed" ? "failed" : data.status === "translating" ? "pending" : "processing",
        stage: data.stage, percent: Number(data.percent || 0), estimated: !complete,
        sourceMessageId: Number(data.source_message_id), result: complete ? String(data.result) : "",
        title: item.title, language: "일본어", updatedAt: Date.now(),
      };
      lyricsStudyKey = key;
      saveLyricsStudyRecord(key, record);
      setLyricsStudyUi(record);
      if (["pending", "processing"].includes(record.status)) scheduleLyricsStudyPoll(key, 1000);
    } else if (!["complete", "failed"].includes(data.status)) {
      $("lyrics-state").textContent = data.stage || "LRC 자동 처리 중";
    }
    if (!["complete", "failed"].includes(data.status) && remoteTrack?.id === selectedRemoteId) {
      window.setTimeout(() => syncAutomaticLyrics(item, selectedRemoteId, attempt + 1), attempt < 20 ? 3000 : 8000);
    }
  } catch (_) {
    if (attempt < 5 && remoteTrack?.id === selectedRemoteId) {
      window.setTimeout(() => syncAutomaticLyrics(item, selectedRemoteId, attempt + 1), 5000);
    }
  }
}

async function loadRemoteAudio(item, autoplay = true, playlistPosition = -1) {
  if (audioUrl?.startsWith("blob:")) URL.revokeObjectURL(audioUrl);
  audioFile = null;
  remoteTrack = item;
  playlistIndex = playlistPosition;
  audioUrl = item.stream_url;
  audio.src = audioUrl;
  preparePlayer(item.title, `${(item.size / 1024 / 1024).toFixed(1)}MB · ${item.library_label || "Mac 보관함"}`);
  updateFavoriteButton();
  renderLrcReviewQueue();
  if ("mediaSession" in navigator) navigator.mediaSession.metadata = new MediaMetadata({ title: item.title, artist: "Mac MP3 보관함" });
  const selectedRemoteId = item.id;
  let lrcUrl = item.lrc_url || "";
  if (!lrcUrl) {
    try {
      const key = favoriteIdentity(item);
      const syncedResponse = await fetch("/api/me/mp3-lrc-index", { credentials: "same-origin", cache: "no-store" });
      const synced = await syncedResponse.json().catch(() => []);
      if (Array.isArray(synced) && synced.some((entry) => entry.key === key)) {
        lrcUrl = `/api/me/mp3-lrc?track_key=${encodeURIComponent(key)}`;
      }
    } catch (_) {}
  }
  if (lrcUrl) {
    try {
      const response = await fetch(lrcUrl, { credentials: "same-origin", cache: "no-store" });
      if (response.ok && remoteTrack?.id === selectedRemoteId) {
        const lrc = new File(
          [await response.text()],
          item.name.replace(/\.mp3$/i, ".lrc"),
          { type: "text/plain;charset=utf-8" },
        );
        await applyLrc(lrc, null);
      }
    } catch (_) {}
  }
  syncAutomaticLyrics(item, selectedRemoteId);
  if (autoplay) audio.play().catch(() => message("재생 버튼을 눌러 시작하세요."));
  renderPlaylist();
  savePlaybackSession();
}

function isFavoritesPlaylistOpen() {
  const name = String(activePlaylistName || "").normalize("NFC").toLocaleLowerCase();
  return name.includes("좋아요") || name.includes("favorite");
}

async function syncFavoritesPlaylist() {
  if (!playlist.length || !isFavoritesPlaylistOpen() || favoritesSyncBusy) return;
  favoritesSyncBusy = true;
  try {
    const response = await fetch("/api/mp3-player/favorites-library", { credentials: "same-origin", cache: "no-store" });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || "좋아요음악 동기화 실패");
    const known = new Set(playlist.map(item => normalizedTrackName(item.file?.name || item.name)));
    const additions = (data.items || []).filter(item => !known.has(normalizedTrackName(item.name))).map(item => ({
      ...item,
      lrcFile: null,
      lyricsLanguage: item.recommended_japanese ? "ja" : "unknown",
      duration: null,
    }));
    const serverCount = (data.items || []).length;
    if (additions.length) {
      playlist.push(...additions);
      renderPlaylist();
      message(`좋아요음악 새 곡 ${additions.length}개를 재생 목록에 동기화했습니다.`);
    }
    favoritesKnownCount = serverCount;
  } catch (_) {
    // 폴더 권한이나 네트워크가 잠시 없으면 다음 주기에 다시 확인한다.
  } finally { favoritesSyncBusy = false; }
}

async function restoreMacPlayback(state) {
  if (!state?.remoteId && !state?.fileName && !state?.title) return false;
  renderRestoreHint(state);
  try {
    const responses = await Promise.all([
      fetch("/api/mp3-player/library", { credentials: "same-origin", cache: "no-store" }),
      fetch("/api/mp3-player/favorites-library", { credentials: "same-origin", cache: "no-store" }),
    ]);
    const payloads = await Promise.all(responses.map(response => response.json().catch(() => ({}))));
    const items = payloads.flatMap(data => data.items || []);
    if (!items.length && responses.every(response => !response.ok)) throw new Error("Mac 보관함을 불러오지 못했습니다");
    const match = items.find((item) => item.id === state.remoteId)
      || items.find((item) => item.name === state.fileName)
      || items.find((item) => item.title === state.title);
    if (!match) throw new Error("최근 곡이 Mac 보관함에서 보이지 않습니다");
    pendingResumeTime = Number(state.time || 0);
    await loadRemoteAudio(match, false);
    $("restore-hint")?.classList.add("hidden");
    message(`${clock(Number(state.time || 0))} 위치를 복구했습니다. 재생 버튼을 눌러 이어 들으세요.`);
    return true;
  } catch (error) {
    $("restore-hint-copy").textContent = `${error.message}. Mac MP3에서 다시 선택해 주세요.`;
    return false;
  }
}

let restorePromise = null;
function restorePlaybackIfNeeded() {
  if (audio.src || audioFile || remoteTrack || playlist.length) return Promise.resolve(false);
  const state = getPlaybackSession();
  if (!state?.title) return Promise.resolve(false);
  renderRestoreHint(state);
  if (state.source !== "mac") return Promise.resolve(false);
  if (!restorePromise) restorePromise = restoreMacPlayback(state).finally(() => { restorePromise = null; });
  return restorePromise;
}

async function loadMacLibrary(open = false) {
  const panel = $("mac-library"), list = $("mac-library-list");
  if (open) panel.classList.remove("hidden");
  list.innerHTML = '<p class="mac-library-empty">보관함을 불러오는 중…</p>';
  try {
    const response = await fetch("/api/mp3-player/library", { credentials: "same-origin" });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || "Mac 보관함을 불러오지 못했습니다");
    list.replaceChildren();
    (data.items || []).forEach(item => {
      const button = document.createElement("button"), copy = document.createElement("span"), title = document.createElement("b"), meta = document.createElement("small"), play = document.createElement("i");
      button.type = "button"; button.className = "mac-library-item";
      title.textContent = item.title; meta.textContent = `${(item.size / 1024 / 1024).toFixed(1)}MB`;
      play.className = "player-icon icon-play"; play.setAttribute("aria-hidden", "true"); copy.append(title, meta); button.append(copy, play);
      button.addEventListener("click", () => loadRemoteAudio(item)); list.append(button);
    });
    if (!(data.items || []).length) list.innerHTML = '<p class="mac-library-empty">받아 둔 MP3가 없습니다.</p>';
    const requested = new URLSearchParams(location.search).get("track");
    const match = requested && (data.items || []).find(item => item.id === requested);
    if (match) { loadRemoteAudio(match, false); history.replaceState({}, "", location.pathname); }
  } catch (error) { list.innerHTML = `<p class="mac-library-empty"></p>`; list.firstChild.textContent = error.message; }
}

function applyRecommendationPreferences(preferences = {}) {
  const form = $("recommendation-preferences");
  for (const input of form.querySelectorAll('input[type="checkbox"]')) {
    input.checked = (preferences[input.name] || []).includes(input.value);
  }
  $("recommendation-artists").value = (preferences.artists || []).join(", ");
}

function recommendationPreferencesFromForm() {
  const form = $("recommendation-preferences");
  return {
    genres: [...form.querySelectorAll('input[name="genres"]:checked')].map(input => input.value),
    moods: [...form.querySelectorAll('input[name="moods"]:checked')].map(input => input.value),
    artists: $("recommendation-artists").value.split(",").map(value => value.trim()).filter(Boolean),
  };
}

async function recommendationApi(path, options = {}) {
  const response = await fetch(path, {
    credentials: "same-origin",
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
  return data;
}

function renderRecommendations(items, append = false) {
  const list = $("recommendations-list");
  if (!append) list.replaceChildren();
  const sortMode = $("recommendation-sort")?.value || "recommended";
  const groupCounts = items.reduce((counts, item) => {
    const key = sortMode === "anime" ? (item.anime_title || "기타 애니송") : sortMode === "artist" ? (item.artist || "가수 정보 없음") : "";
    if (key) counts.set(key, (counts.get(key) || 0) + 1); return counts;
  }, new Map());
  let previousGroup = "";
  for (const item of items) {
    const group = sortMode === "anime" ? (item.anime_title || "기타 애니송") : sortMode === "artist" ? (item.artist || "가수 정보 없음") : "";
    if (group && group !== previousGroup) {
      const heading = document.createElement("button"), label = document.createElement("span"), arrow = document.createElement("i");
      heading.type = "button"; heading.className = "recommendation-group-title"; label.textContent = `${group} · ${groupCounts.get(group) || 0}곡`; arrow.textContent = "⌄";
      heading.setAttribute("aria-expanded", String(!collapsedRecommendationGroups.has(group)));
      heading.addEventListener("click", () => {
        const collapsed = !collapsedRecommendationGroups.has(group);
        if (collapsed) collapsedRecommendationGroups.add(group); else collapsedRecommendationGroups.delete(group);
        heading.setAttribute("aria-expanded", String(!collapsed));
        for (const groupedCard of list.querySelectorAll(".recommendation-card")) {
          if (groupedCard.dataset.recommendationGroup === group) groupedCard.classList.toggle("hidden", collapsed);
        }
      });
      heading.append(label, arrow);
      list.append(heading); previousGroup = group;
    }
    const card = document.createElement("article"), image = document.createElement("img"), copy = document.createElement("div");
    const title = document.createElement("b"), artist = document.createElement("small"), reason = document.createElement("p"), actions = document.createElement("div");
    const preview = document.createElement("button"), youtube = document.createElement("a"), download = document.createElement("button"), dismiss = document.createElement("button");
    const progress = document.createElement("div"), progressHead = document.createElement("div"), progressStage = document.createElement("span"), progressPercent = document.createElement("b"), progressTrack = document.createElement("div"), progressBar = document.createElement("i");
    card.className = "recommendation-card"; card.dataset.youtubeId = item.youtube_id; copy.className = "recommendation-copy"; actions.className = "recommendation-actions";
    if (group) { card.dataset.recommendationGroup = group; card.classList.toggle("hidden", collapsedRecommendationGroups.has(group)); }
    image.src = item.thumbnail; image.alt = ""; image.loading = "lazy"; title.textContent = item.title;
    artist.textContent = item.artist || "YouTube Music";
    if (Number(item.view_count || 0) > 0) {
      const views = document.createElement("span"); views.className = "recommendation-views";
      views.textContent = `조회수 ${new Intl.NumberFormat("ko-KR", { notation: "compact", maximumFractionDigits: 1 }).format(item.view_count)}회`;
      artist.append(views);
    }
    reason.className = "recommendation-reason";
    reason.textContent = (item.reasons || []).join(" · ") || "새로운 일본 노래 탐색";
    preview.type = "button"; preview.className = "preview"; preview.textContent = "화면에서 재생";
    youtube.href = item.source_url; youtube.target = "_blank"; youtube.rel = "noopener"; youtube.textContent = "YouTube";
    download.type = "button"; download.className = "download"; download.textContent = "MP3로 추가";
    dismiss.type = "button"; dismiss.textContent = "관심 없음";
    progress.className = "recommendation-download-progress hidden"; progressHead.className = "recommendation-download-head";
    progressStage.textContent = "다운로드 대기 중"; progressPercent.textContent = "0%"; progressTrack.className = "recommendation-download-track"; progressBar.style.width = "0%";
    progressHead.append(progressStage, progressPercent); progressTrack.append(progressBar); progress.append(progressHead, progressTrack);
    preview.addEventListener("click", () => {
      const currentPlayer = card.querySelector(".recommendation-player");
      document.querySelectorAll(".recommendation-player").forEach(player => {
        const owner = player.closest(".recommendation-card");
        owner?.querySelector(".preview")?.replaceChildren("화면에서 재생");
        player.remove();
      });
      if (currentPlayer) return;
      const player = document.createElement("div"), frame = document.createElement("iframe");
      player.className = "recommendation-player";
      frame.src = `https://www.youtube-nocookie.com/embed/${encodeURIComponent(item.youtube_id)}?autoplay=1&playsinline=1&rel=0`;
      frame.title = `${item.title} YouTube 재생`;
      frame.allow = "autoplay; encrypted-media; picture-in-picture";
      frame.allowFullscreen = true;
      player.append(frame); card.prepend(player); preview.textContent = "재생 닫기";
      player.scrollIntoView({ behavior: "smooth", block: "nearest" });
    });
    download.addEventListener("click", async () => {
      card.classList.add("busy");
      download.disabled = true; progress.classList.remove("hidden", "failed");
      try {
        const job = await recommendationApi("/api/shift-alarm/youtube-mp3", { method: "POST", body: JSON.stringify({ url: item.source_url, destination: "favorites" }) });
        await recommendationApi("/api/mp3-recommendations/feedback", { method: "POST", body: JSON.stringify({ youtube_id: item.youtube_id, action: "download", title: item.title }) });
        download.textContent = "대기 중 0%"; updateRecommendationDownloadProgress(card, job);
        pollRecommendationDownload(item, card, job.id); message(`${item.title}을 좋아요음악 폴더에 저장합니다.`);
      } catch (error) { card.classList.remove("busy"); download.disabled = false; download.textContent = "다시 시도"; progress.classList.add("failed"); progressStage.textContent = error.message; message(error.message, true); }
    });
    dismiss.addEventListener("click", async () => {
      card.classList.add("busy");
      try {
        await recommendationApi("/api/mp3-recommendations/feedback", { method: "POST", body: JSON.stringify({ youtube_id: item.youtube_id, action: "dismiss", title: item.title }) });
        card.remove(); message("이 곡은 다음 추천에서 제외합니다.");
      } catch (error) { card.classList.remove("busy"); message(error.message, true); }
    });
    actions.append(preview, download, dismiss, youtube); copy.append(title, artist, reason, actions, progress); card.append(image, copy); list.append(card);
  }
  restoreRecommendationDownloadStates();
  if (!items.length) $("recommendations-state").textContent = "새 후보를 찾지 못했습니다. 장르나 가수를 바꿔 다시 시도해보세요.";
}

function sortedRecommendationItems() {
  const mode = $("recommendation-sort")?.value || "recommended";
  const items = [...recommendationItems];
  if (mode === "views") return items.sort((a, b) => Number(b.view_count || 0) - Number(a.view_count || 0) || Number(b.score || 0) - Number(a.score || 0));
  if (mode === "anime") return items.sort((a, b) => (a.anime_title || "기타 애니송").localeCompare(b.anime_title || "기타 애니송", "ja") || Number(b.view_count || 0) - Number(a.view_count || 0));
  if (mode === "artist") return items.sort((a, b) => (a.artist || "가수 정보 없음").localeCompare(b.artist || "가수 정보 없음", "ja") || Number(b.view_count || 0) - Number(a.view_count || 0));
  return items;
}

function rerenderRecommendationSort() {
  renderRecommendations(sortedRecommendationItems(), false);
  if (recommendationItems.length) $("recommendations-state").textContent = `${recommendationTotal || recommendationItems.length}곡 중 ${recommendationItems.length}곡을 표시했습니다.`;
}

function updateRecommendationDownloadProgress(card, job = {}) {
  const panel = card.querySelector(".recommendation-download-progress"), stage = card.querySelector(".recommendation-download-head span");
  const percentLabel = card.querySelector(".recommendation-download-head b"), bar = card.querySelector(".recommendation-download-track i"), button = card.querySelector(".download");
  const percent = Math.max(0, Math.min(100, Number(job.percent || 0)));
  panel.classList.remove("hidden"); stage.textContent = job.stage || job.message || "저장 처리 중";
  percentLabel.textContent = `${percent}%`; bar.style.width = `${percent}%`;
  if (!["complete", "failed"].includes(job.status)) button.textContent = `${job.stage || "저장 중"} ${percent}%`;
}

function addDownloadedFavoriteToPlaylist(item) {
  if (!item?.id || playlist.some(track => track.id === item.id || normalizedTrackName(track.file?.name || track.name) === normalizedTrackName(item.name))) return;
  playlist.push({ ...item, lrcFile: null, lyricsLanguage: item.recommended_japanese ? "ja" : "unknown", duration: null });
  renderPlaylist(); savePlaybackSession();
}

async function pollRecommendationDownload(item, card, jobId) {
  if (!jobId || !card.isConnected) return;
  try {
    const result = await recommendationApi(`/api/shift-alarm/youtube-mp3?job_id=${encodeURIComponent(jobId)}`);
    const job = result.job || {};
    updateRecommendationDownloadProgress(card, job);
    const button = card.querySelector(".download"), panel = card.querySelector(".recommendation-download-progress");
    if (job.status === "complete" && result.item) {
      card.classList.remove("busy"); card.classList.add("saved"); button.disabled = true; button.textContent = "저장됨 ✓";
      addDownloadedFavoriteToPlaylist(result.item);
      message(`${item.title} 저장이 완료되어 재생 목록에 추가했습니다.`);
      return;
    }
    if (job.status === "failed") {
      card.classList.remove("busy"); button.disabled = false; button.textContent = "다시 시도"; panel.classList.add("failed");
      message(job.error || "MP3 저장에 실패했습니다.", true); return;
    }
    window.setTimeout(() => pollRecommendationDownload(item, card, jobId), 1200);
  } catch (_) {
    window.setTimeout(() => pollRecommendationDownload(item, card, jobId), 3000);
  }
}

async function restoreRecommendationDownloadStates() {
  try {
    const data = await recommendationApi("/api/shift-alarm/youtube-mp3");
    for (const card of document.querySelectorAll(".recommendation-card[data-youtube-id]")) {
      const job = (data.jobs || []).find(entry => entry.youtube_id === card.dataset.youtubeId);
      if (!job) continue;
      const button = card.querySelector(".download");
      if (job.status === "complete") {
        updateRecommendationDownloadProgress(card, job); card.classList.add("saved"); button.disabled = true; button.textContent = "저장됨 ✓";
      } else if (job.status === "failed") {
        updateRecommendationDownloadProgress(card, job); card.querySelector(".recommendation-download-progress").classList.add("failed"); button.textContent = "다시 시도";
      } else {
        card.classList.add("busy"); button.disabled = true; updateRecommendationDownloadProgress(card, job);
        pollRecommendationDownload({ title: card.querySelector(".recommendation-copy>b")?.textContent || "곡" }, card, job.id);
      }
    }
  } catch (_) {}
}

function rememberRecommendationsReturn() {
  try { sessionStorage.setItem(RECOMMENDATIONS_RETURN_KEY, JSON.stringify({ active: true, scrollY: Number(window.scrollY || 0) })); }
  catch (_) {}
}

function clearRecommendationsReturn() {
  try { sessionStorage.removeItem(RECOMMENDATIONS_RETURN_KEY); } catch (_) {}
}

function getRecommendationsReturn() {
  try { return JSON.parse(sessionStorage.getItem(RECOMMENDATIONS_RETURN_KEY) || "null"); }
  catch (_) { return null; }
}

async function openRecommendations(options = {}) {
  if (!options?.restore) {
    rememberRecommendationsReturn();
    if (history.state?.mp3View !== "recommendations") {
      history.pushState({ ...(history.state || {}), mp3View: "recommendations" }, "", location.href);
    }
  }
  $("mac-library").classList.add("hidden");
  $("recommendations").classList.remove("hidden");
  document.documentElement.classList.add("recommendations-active");
  $("recommendations-state").textContent = "저장된 취향을 불러오는 중…";
  try {
    const preferences = await recommendationApi("/api/mp3-recommendations/preferences");
    applyRecommendationPreferences(preferences);
    const now = new Date(), year = now.getFullYear();
    if (!$('recommendation-year').options.length) {
      for (let value = year; value >= year - 5; value -= 1) {
        const option = document.createElement("option"); option.value = String(value); option.textContent = `${value}년`;
        $("recommendation-year").append(option);
      }
    }
    $("recommendation-year").value = String(year);
    $("recommendation-season").value = now.getMonth() < 3 ? "WINTER" : now.getMonth() < 6 ? "SPRING" : now.getMonth() < 9 ? "SUMMER" : "FALL";
    updateRecommendationModeUi();
    $("recommendations-state").textContent = "취향을 확인하고 추천 받기를 눌러주세요.";
  } catch (error) { $("recommendations-state").textContent = error.message; }
}

async function returnToRecommendations(event = null) {
  const saved = getRecommendationsReturn();
  if (!saved?.active) return false;
  event?.preventDefault();
  $("player").classList.add("hidden");
  $("empty").classList.remove("hidden");
  await openRecommendations({ restore: true });
  window.requestAnimationFrame(() => {
    const top = Number(saved.scrollY || 0);
    window.scrollTo({ top, behavior: "auto" });
    if (!top) $("recommendations").scrollIntoView({ block: "start" });
  });
  return true;
}

async function refreshRecommendations(event) {
  event?.preventDefault();
  const button = $("recommendations-refresh");
  button.disabled = true; $("recommendations-state").textContent = "일본 노래 후보를 찾는 중… 잠시만 기다려주세요.";
  try {
    const preferences = await recommendationApi("/api/mp3-recommendations/preferences", { method: "PUT", body: JSON.stringify(recommendationPreferencesFromForm()) });
    applyRecommendationPreferences(preferences);
    recommendationCursor = 0;
    const result = await loadRecommendationPage(false);
    if ((result.items || []).length) $("recommendations-state").textContent = `${result.total || result.items.length}곡 중 ${result.items.length}곡을 표시했습니다. 아래로 내리면 더 불러옵니다.`;
  } catch (error) { $("recommendations-state").textContent = error.message; message(error.message, true); }
  finally { button.disabled = false; }
}

function selectedRecommendationMode() {
  return document.querySelector('input[name="recommendation-mode"]:checked')?.value || "taste";
}

function updateRecommendationModeUi() {
  const mode = selectedRecommendationMode();
  $("recommendation-season-fields").classList.toggle("hidden", mode !== "season");
  $("recommendations-refresh").textContent = mode === "popular" ? "인기 애니송 추천 받기" : mode === "season" ? "분기 OST 추천 받기" : "취향 저장하고 추천 받기";
}

async function loadRecommendationPage(append = true) {
  if (recommendationLoading || recommendationCursor === null && append) return { items: [] };
  recommendationLoading = true;
  const more = $("recommendations-more");
  more.disabled = true; more.textContent = "추천곡 불러오는 중…";
  try {
    const mode = selectedRecommendationMode();
    const params = new URLSearchParams({ mode, cursor: String(append ? recommendationCursor || 0 : 0), page_size: "12" });
    if (mode === "season") {
      params.set("year", $("recommendation-year").value);
      params.set("season", $("recommendation-season").value);
    }
    const result = await recommendationApi(`/api/mp3-recommendations?${params}`);
    let addedItems = [];
    if (append) {
      const known = new Set(recommendationItems.map(item => item.youtube_id));
      addedItems = (result.items || []).filter(item => !known.has(item.youtube_id));
      recommendationItems.push(...addedItems);
    } else {
      recommendationItems = [...(result.items || [])];
      $("recommendation-sort").value = "recommended";
    }
    $("recommendation-sort-row").classList.toggle("hidden", !recommendationItems.length);
    if (append && $("recommendation-sort").value === "recommended") {
      renderRecommendations(addedItems, true);
    } else {
      const scrollTop = window.scrollY;
      renderRecommendations(sortedRecommendationItems(), false);
      if (append) window.requestAnimationFrame(() => window.scrollTo({ top: scrollTop, behavior: "auto" }));
    }
    recommendationCursor = result.next_cursor ?? null;
    recommendationTotal = Number(result.total || 0);
    more.classList.toggle("hidden", recommendationCursor === null);
    more.disabled = false; more.textContent = "추천 곡 더 보기";
    if (append && (result.items || []).length) {
      $("recommendations-state").textContent = `${recommendationTotal}곡 중 ${recommendationItems.length}곡을 표시했습니다.`;
    } else if (append && recommendationCursor === null) {
      $("recommendations-state").textContent = "추천곡을 모두 확인했습니다.";
    }
    return result;
  } finally {
    recommendationLoading = false;
    more.disabled = false;
  }
}

async function applyLrc(file, expectedAudioFile = audioFile) {
  if (!file) return;
  try {
    const nextLrc = await file.text();
    const nextRows = parseLrc(nextLrc);
    if (expectedAudioFile !== audioFile) return;
    currentLrc = nextLrc;
    lyricRows = nextRows;
    if (!lyricRows.length) throw new Error("시간 태그가 없습니다");
    attachLrcToCurrentTrack(currentLrc);
    const item = playlistIndex >= 0 ? playlist[playlistIndex] : (remoteTrack || audioFile);
    const resolved = resolveTrackLyricsLanguage(item, currentLrc);
    if (resolved.mismatch) {
      currentLrc = "";
      lyricRows = [];
      if (item) item.lrcLanguageMismatch = true;
      throw new Error("한국어 곡인데 기존 LRC가 일본어로 잘못 인식됐습니다. LRC 재생성으로 바로잡아 주세요");
    }
    updateGenerateButton();
    renderLyrics(); syncLyrics(true); message("LRC 가사를 적용했습니다.");
  } catch (error) { currentLrc = ""; lyricRows = []; updateGenerateButton(); updateLyricsStudyButton(); message(`LRC를 읽지 못했습니다: ${error.message}`, true); }
}

async function generateLrc() {
  if (!audioFile && !remoteTrack) { message("재생 중인 MP3를 찾지 못했습니다.", true); return false; }
  const button = $("generate");
  const landscapeButton = $("landscape-regenerate");
  const previousLrc = currentLrc;
  const previousRows = lyricRows;
  button.disabled = true; button.textContent = "Whisper 분석 중…";
  landscapeButton.disabled = true;
  landscapeButton.classList.add("working");
  $("lyrics-state").textContent = "Mac에서 가사 생성 중";
  try {
    const job = await submitLrcJob(
      playlistIndex >= 0 ? playlist[playlistIndex] : (remoteTrack || audioFile),
    );
    currentLrc = await waitForLrcJob(job, null);
    showLrcProgress("3/3 · 새 LRC 적용 중", "95%", 95);
    lyricRows = parseLrc(currentLrc);
    if (lyricRows.length < 2) throw new Error("가사를 충분히 인식하지 못했습니다. 잘못된 한 줄 가사는 적용하지 않았습니다.");
    attachLrcToCurrentTrack(currentLrc);
    if (playlistIndex >= 0) removeActiveLrcJobsForKey(reviewTrackKey(playlist[playlistIndex]));
    updateGenerateButton();
    renderLyrics(); syncLyrics(true);
    $("download-lrc").classList.remove("hidden");
    showLrcProgress("완료 · 새 가사 적용됨", "100%", 100);
    message("LRC 가사를 만들었습니다. 필요하면 파일로 저장하세요.");
    return true;
  } catch (error) {
    currentLrc = previousLrc;
    lyricRows = previousRows;
    updateLyricsStudyButton();
    $("lyrics-state").textContent = "생성 실패";
    showLrcProgress("생성 실패", error.message, 0);
    message(error.message, true);
    return false;
  } finally {
    button.disabled = false;
    landscapeButton.disabled = false;
    landscapeButton.classList.remove("working");
    updateGenerateButton();
  }
}

async function runLrcReviewQueue() {
  if (reviewRunning) return;
  const queued = getLrcReviewQueue();
  const jobs = queued
    .map((entry) => ({ entry, index: playlist.findIndex((item) => reviewTrackKey(item) === entry.key) }))
    .filter((job) => job.index >= 0);
  if (!jobs.length) {
    message("검토할 곡이 현재 플레이리스트에 없습니다. 해당 폴더를 다시 열어주세요.", true);
    return;
  }
  reviewRunning = true;
  renderLrcReviewQueue();
  let completed = 0;
  for (const job of jobs) {
    loadPlaylistTrack(job.index, false);
    message(`LRC 검토 작업 등록 ${completed + 1}/${jobs.length} · ${job.entry.title}`);
    try {
      await submitLrcJob(playlist[job.index]);
      const remaining = getLrcReviewQueue().filter((entry) => entry.key !== job.entry.key);
      saveLrcReviewQueue(remaining);
      completed += 1;
    } catch (error) {
      message(`${job.entry.title} 등록 실패: ${error.message}`, true);
      break;
    }
  }
  reviewRunning = false;
  renderLrcReviewQueue();
  if (completed === jobs.length) {
    message(`LRC 검토 ${completed}곡을 서버에 등록했습니다. 이제 앱을 닫아도 계속됩니다.`);
    recoverLrcJobs();
  }
}

function downloadLrc() {
  if (!currentLrc) return;
  const filename = trackFilename(playlistIndex >= 0 ? playlist[playlistIndex] : (remoteTrack || audioFile));
  if (!filename) return;
  const url = URL.createObjectURL(new Blob([currentLrc], { type: "text/plain;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url; link.download = filename.replace(/\.mp3$/i, ".lrc");
  document.body.append(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 30000);
}

$("audio-file").addEventListener("change", () => setPlaylist($("audio-file").files));
$("folder-files").addEventListener("change", () => setPlaylist($("folder-files").files));
$("replace-file").addEventListener("change", () => setPlaylist($("replace-file").files, true));
$("recent-playlist").addEventListener("click", () => {
  message("iPhone 보안 확인 후 같은 폴더의 ‘열기’를 눌러주세요.");
  $("folder-files").click();
});
$("mac-library-open").addEventListener("click", () => loadMacLibrary(true));
$("mac-library-refresh").addEventListener("click", () => loadMacLibrary(true));
$("recommendations-open").addEventListener("click", openRecommendations);
$("recommendations-close").addEventListener("click", () => {
  $("recommendations").classList.add("hidden");
  document.documentElement.classList.remove("recommendations-active");
  clearRecommendationsReturn();
});
const appBack = document.querySelector("body > header > a");
if (appBack) {
  appBack.id = "app-back";
  appBack.setAttribute("aria-label", "이전 화면으로 돌아가기");
  appBack.addEventListener("click", (event) => { void returnToRecommendations(event); });
}
window.addEventListener("popstate", (event) => {
  if (getRecommendationsReturn()?.active) {
    void returnToRecommendations(event);
  }
});
$("recommendation-preferences").addEventListener("submit", refreshRecommendations);
document.querySelectorAll('input[name="recommendation-mode"]').forEach(input => input.addEventListener("change", updateRecommendationModeUi));
$("recommendation-sort").addEventListener("change", rerenderRecommendationSort);
$("recommendations-more").addEventListener("click", () => loadRecommendationPage(true).catch(error => message(error.message, true)));
new IntersectionObserver((entries) => {
  if (entries.some(entry => entry.isIntersecting) && !$("recommendations").classList.contains("hidden") && recommendationCursor !== null) {
    loadRecommendationPage(true).catch(error => message(error.message, true));
  }
}, { rootMargin: "500px 0px" }).observe($("recommendations-sentinel"));
window.addEventListener("scroll", () => {
  if ($("recommendations").classList.contains("hidden") || recommendationCursor === null || recommendationLoading) return;
  if (window.scrollY + window.innerHeight >= document.documentElement.scrollHeight - 700) {
    loadRecommendationPage(true).catch(error => message(error.message, true));
  }
}, { passive: true });
$("lrc-file").addEventListener("change", () => applyLrc($("lrc-file").files?.[0]));
$("generate").addEventListener("click", generateLrc);
$("landscape-regenerate").addEventListener("click", generateLrc);
$("landscape-review").addEventListener("click", () => {
  setCurrentLrcReviewRequested($("landscape-review").getAttribute("aria-pressed") !== "true");
});
$("download-lrc").addEventListener("click", downloadLrc);
$("lyrics-study").addEventListener("click", requestLyricsStudy);
$("favorite-track").addEventListener("click", toggleCurrentFavorite);
$("lrc-review-check").addEventListener("change", () => {
  setCurrentLrcReviewRequested($("lrc-review-check").checked);
});
$("lrc-review-start").addEventListener("click", runLrcReviewQueue);
$("play").addEventListener("click", () => audio.paused ? audio.play().catch(() => message("재생을 시작하지 못했습니다.", true)) : audio.pause());
$("back").addEventListener("click", () => { audio.currentTime = Math.max(0, audio.currentTime - 10); });
$("forward").addEventListener("click", () => { audio.currentTime = Math.min(audio.duration || Infinity, audio.currentTime + 10); });
$("previous-track").addEventListener("click", () => playAdjacent(-1));
$("next-track").addEventListener("click", () => playAdjacent(1));
$("lyrics-card").addEventListener("pointerdown", beginLandscapeLyricsSwipe);
$("lyrics-card").addEventListener("pointerup", finishLandscapeLyricsSwipe);
$("lyrics-card").addEventListener("pointercancel", () => { landscapeSwipe = null; });
$("seek").addEventListener("input", () => { if (audio.duration) audio.currentTime = audio.duration * Number($("seek").value) / 1000; });
$("rate").addEventListener("change", () => { audio.playbackRate = Number($("rate").value); savePlaybackSession(); });
$("lyric-size").addEventListener("click", () => {
  const current = $("lyric-size").dataset.size || "normal";
  setLyricSize(LYRIC_SIZES[(LYRIC_SIZES.indexOf(current) + 1) % LYRIC_SIZES.length]);
});
$("theme-toggle").addEventListener("click", () => {
  setTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
});
$("follow").addEventListener("click", () => { followLyrics = !followLyrics; $("follow").textContent = `자동 스크롤 ${followLyrics ? "켬" : "끔"}`; $("follow").setAttribute("aria-pressed", String(followLyrics)); savePlaybackSession(); });
$("lyrics-toggle").addEventListener("click", () => {
  const collapsed = !$("lyrics-card").classList.contains("collapsed");
  setLyricsCollapsed(collapsed);
  if (!collapsed) $("lyrics-card").scrollIntoView({ behavior: "smooth", block: "nearest" });
});
$("playlist-toggle").addEventListener("click", () => {
  const body = $("playlist-body"); const opening = body.classList.contains("hidden");
  body.classList.toggle("hidden"); $("playlist-toggle").setAttribute("aria-expanded", String(opening));
  if (opening) renderPlaylist();
});
$("playlist-clear").addEventListener("click", () => {
  playlist = []; playlistIndex = -1; shuffleHistory = []; shuffleHistoryCursor = -1; audio.pause(); audio.removeAttribute("src");
  $("player").classList.add("hidden"); $("empty").classList.remove("hidden"); renderPlaylist();
});
$("playlist-favorites").addEventListener("click", () => {
  favoritesOnly = !favoritesOnly;
  $("playlist-favorites").setAttribute("aria-pressed", String(favoritesOnly));
  $("playlist-favorites").textContent = favoritesOnly ? "전체 목록" : "즐겨찾기만";
  renderPlaylist();
  if (favoritesOnly && playlistIndex >= 0 && !playlistEligibleEntries().some(({ index }) => index === playlistIndex)) {
    const firstFavorite = playlistEligibleEntries()[0]?.index ?? -1;
    if (firstFavorite >= 0) loadPlaylistTrack(firstFavorite, true);
  }
  savePlaybackSession();
});
$("playlist-filter").addEventListener("change", async () => {
  const select = $("playlist-filter");
  playlistViewMode = select.value;
  localStorage.setItem(PLAYLIST_FILTER_KEY, playlistViewMode);
  savePlaybackSession();
  select.disabled = true;
  try {
    await preparePlaylistFilter(playlistViewMode);
    const eligible = playlistEligibleEntries();
    renderPlaylist();
    if (!eligible.length) {
      message("선택한 조건에 맞는 곡이 없습니다.", true);
      return;
    }
    if (playlistViewMode.endsWith("-asc") || !eligible.some(({ index }) => index === playlistIndex)) loadPlaylistTrack(eligible[0].index, true);
    else message(`${eligible.length}곡에 필터를 적용했습니다.`);
  } finally { select.disabled = false; }
});
$("playlist-prev").addEventListener("click", () => playAdjacent(-1));
$("playlist-next").addEventListener("click", () => playAdjacent(1));
$("playlist-shuffle").addEventListener("click", () => {
  setShuffle(!shufflePlaylist);
});
$("shuffle-main").addEventListener("click", () => setShuffle(!shufflePlaylist));
$("playlist-repeat").addEventListener("click", () => {
  setRepeatMode(repeatMode === "all" ? "one" : repeatMode === "one" ? "off" : "all");
});
$("lrc-retry").addEventListener("click", () => { void retryLrcFailure(); });
$("lrc-dismiss").addEventListener("click", dismissLrcFailure);
audio.addEventListener("loadedmetadata", () => {
  $("duration").textContent = clock(audio.duration);
  if (playlistIndex >= 0 && playlist[playlistIndex] && Number.isFinite(audio.duration)) {
    playlist[playlistIndex].duration = audio.duration;
  }
  if (pendingResumeTime > 0) {
    audio.currentTime = Math.min(pendingResumeTime, Math.max(0, (audio.duration || pendingResumeTime) - 0.5));
    pendingResumeTime = 0;
  }
});
audio.addEventListener("timeupdate", () => { $("current").textContent = clock(audio.currentTime); $("seek").value = audio.duration ? String(Math.round(audio.currentTime / audio.duration * 1000)) : "0"; syncLyrics(); savePlaybackPosition(); });
audio.addEventListener("play", () => savePlaybackPosition(true));
audio.addEventListener("ratechange", () => savePlaybackSession());
audio.addEventListener("play", () => { $("play-icon").className = "player-icon icon-pause"; $("play").setAttribute("aria-label", "일시정지"); });
audio.addEventListener("pause", () => { $("play-icon").className = "player-icon icon-play"; $("play").setAttribute("aria-label", "재생"); savePlaybackPosition(true); });
audio.addEventListener("ended", () => {
  if (repeatMode === "one" && playlistIndex >= 0) { audio.currentTime = 0; audio.play().catch(() => {}); return; }
  playAdjacent(1);
});
window.addEventListener("pagehide", () => savePlaybackPosition(true));
window.addEventListener("pageshow", () => { void restorePlaybackIfNeeded(); });
window.addEventListener("resize", fitVisibleLyrics, { passive: true });
window.addEventListener("orientationchange", () => window.setTimeout(fitVisibleLyrics, 120), { passive: true });
document.fonts?.ready?.then(fitVisibleLyrics).catch(() => {});
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "hidden") savePlaybackPosition(true);
  else { void restorePlaybackIfNeeded(); void syncFavoritesPlaylist(); }
});
window.setInterval(() => { if (document.visibilityState === "visible") void syncFavoritesPlaylist(); }, 8000);
if ("mediaSession" in navigator) {
  navigator.mediaSession.setActionHandler("play", () => audio.play());
  navigator.mediaSession.setActionHandler("pause", () => audio.pause());
  navigator.mediaSession.setActionHandler("seekbackward", () => { audio.currentTime = Math.max(0, audio.currentTime - 10); });
  navigator.mediaSession.setActionHandler("seekforward", () => { audio.currentTime = Math.min(audio.duration || Infinity, audio.currentTime + 10); });
  navigator.mediaSession.setActionHandler("previoustrack", () => playAdjacent(-1));
  navigator.mediaSession.setActionHandler("nexttrack", () => playAdjacent(1));
}
if (new URLSearchParams(location.search).has("track")) loadMacLibrary(false);
showRecentPlaylistShortcut();
setTheme(localStorage.getItem(THEME_KEY)
  || (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"));
setLyricSize(localStorage.getItem(LYRIC_SIZE_KEY) || "xlarge");
setLyricsCollapsed(localStorage.getItem(LYRICS_COLLAPSED_KEY) === "1");
const initialPlaybackMode = savedPlaybackMode();
const initialSession = getPlaybackSession();
setShuffle(Boolean(initialSession?.shuffle ?? initialPlaybackMode.shuffle), false);
setRepeatMode(initialSession?.repeat || initialPlaybackMode.repeat || "all", false);
playlistViewMode = initialSession?.filter || localStorage.getItem(PLAYLIST_FILTER_KEY) || "all";
if (![...$("playlist-filter").options].some((option) => option.value === playlistViewMode)) playlistViewMode = "all";
$("playlist-filter").value = playlistViewMode;
favoritesOnly = Boolean(initialSession?.favoritesOnly);
$("playlist-favorites").setAttribute("aria-pressed", String(favoritesOnly));
$("playlist-favorites").textContent = favoritesOnly ? "전체 목록" : "즐겨찾기만";
followLyrics = initialSession?.followLyrics !== false;
$("follow").textContent = `자동 스크롤 ${followLyrics ? "켬" : "끔"}`;
$("follow").setAttribute("aria-pressed", String(followLyrics));
if (Number.isFinite(Number(initialSession?.rate))) {
  const rate = String(initialSession.rate);
  if ([...$("rate").options].some((option) => option.value === rate)) $("rate").value = rate;
  audio.playbackRate = Number(initialSession.rate);
}
renderLrcReviewQueue();
updateFavoriteButton();
recoverLrcJobs();
void loadSyncedFavorites();
if (new URLSearchParams(location.search).has("recent") && getRecentPlaylist()) {
  message("최근 플레이리스트를 다시 열려면 아래 바로가기를 눌러주세요.");
}
renderRestoreHint(initialSession);
void restorePlaybackIfNeeded();
