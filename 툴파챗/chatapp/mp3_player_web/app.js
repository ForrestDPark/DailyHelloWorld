const $ = (id) => document.getElementById(id);
const audio = $("audio");
let audioFile = null;
let audioUrl = "";
let lyricRows = [];
let activeLyric = -1;
let followLyrics = true;
let currentLrc = "";

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
    return;
  }
  lyricRows.forEach((row, index) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "lyric-line";
    button.dataset.index = index;
    button.textContent = row.text;
    button.addEventListener("click", () => {
      audio.currentTime = row.time;
      audio.play().catch(() => {});
      syncLyrics(true);
    });
    root.append(button);
  });
  $("lyrics-state").textContent = `${lyricRows.length}줄 · 동기화됨`;
  $("lyrics-toggle").disabled = false;
}

function syncLyrics(force = false) {
  if (!lyricRows.length) return;
  let next = -1;
  for (let index = 0; index < lyricRows.length; index += 1) {
    if (lyricRows[index].time <= audio.currentTime + 0.08) next = index;
    else break;
  }
  if (!force && next === activeLyric) return;
  $("lyrics").querySelectorAll(".active").forEach((node) => node.classList.remove("active"));
  activeLyric = next;
  if (next < 0) return;
  const node = $("lyrics").querySelector(`[data-index="${next}"]`);
  node?.classList.add("active");
  if (followLyrics || force) node?.scrollIntoView({ block: "center", behavior: force ? "auto" : "smooth" });
}

function loadAudio(file) {
  if (!file || (!/\.mp3$/i.test(file.name) && file.type !== "audio/mpeg")) {
    message("MP3 파일을 선택해 주세요.", true); return;
  }
  if (audioUrl) URL.revokeObjectURL(audioUrl);
  audioFile = file;
  audioUrl = URL.createObjectURL(file);
  audio.src = audioUrl;
  lyricRows = []; currentLrc = ""; activeLyric = -1;
  $("title").textContent = file.name.replace(/\.mp3$/i, "");
  $("meta").textContent = `${(file.size / 1024 / 1024).toFixed(1)}MB · 기기에서 재생`;
  $("empty").classList.add("hidden");
  $("player").classList.remove("hidden");
  $("download-lrc").classList.add("hidden");
  $("lyrics-toggle").disabled = true;
  $("lyrics-state").textContent = "가사를 불러오세요";
  $("lyrics").innerHTML = '<p class="lyrics-empty">LRC 파일을 적용하거나<br>로컬 Whisper로 만들어 보세요.</p>';
  if ("mediaSession" in navigator) navigator.mediaSession.metadata = new MediaMetadata({ title: $("title").textContent, artist: "기기 MP3" });
}

async function applyLrc(file) {
  if (!file) return;
  try {
    currentLrc = await file.text();
    lyricRows = parseLrc(currentLrc);
    if (!lyricRows.length) throw new Error("시간 태그가 없습니다");
    renderLyrics(); syncLyrics(true); message("LRC 가사를 적용했습니다.");
  } catch (error) { message(`LRC를 읽지 못했습니다: ${error.message}`, true); }
}

async function generateLrc() {
  if (!audioFile) return;
  const button = $("generate");
  const form = new FormData();
  form.append("file", audioFile, audioFile.name);
  button.disabled = true; button.textContent = "Whisper 분석 중…";
  $("lyrics-state").textContent = "Mac에서 가사 생성 중";
  try {
    const response = await fetch("/api/mp3-player/generate-lrc", { method: "POST", credentials: "same-origin", body: form });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(data.detail || `HTTP ${response.status}`);
    }
    currentLrc = await response.text();
    lyricRows = parseLrc(currentLrc);
    if (lyricRows.length < 2) throw new Error("가사를 충분히 인식하지 못했습니다. 잘못된 한 줄 가사는 적용하지 않았습니다.");
    renderLyrics(); syncLyrics(true);
    $("download-lrc").classList.remove("hidden");
    message("LRC 가사를 만들었습니다. 필요하면 파일로 저장하세요.");
  } catch (error) {
    $("lyrics-state").textContent = "생성 실패";
    message(error.message, true);
  } finally { button.disabled = false; button.textContent = "일본어 가사 LRC 생성"; }
}

function downloadLrc() {
  if (!currentLrc || !audioFile) return;
  const url = URL.createObjectURL(new Blob([currentLrc], { type: "text/plain;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url; link.download = `${audioFile.name.replace(/\.mp3$/i, "")}.lrc`;
  document.body.append(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 30000);
}

[$("audio-file"), $("replace-file")].forEach((input) => input.addEventListener("change", () => loadAudio(input.files?.[0])));
$("lrc-file").addEventListener("change", () => applyLrc($("lrc-file").files?.[0]));
$("generate").addEventListener("click", generateLrc);
$("download-lrc").addEventListener("click", downloadLrc);
$("play").addEventListener("click", () => audio.paused ? audio.play().catch(() => message("재생을 시작하지 못했습니다.", true)) : audio.pause());
$("back").addEventListener("click", () => { audio.currentTime = Math.max(0, audio.currentTime - 10); });
$("forward").addEventListener("click", () => { audio.currentTime = Math.min(audio.duration || Infinity, audio.currentTime + 10); });
$("seek").addEventListener("input", () => { if (audio.duration) audio.currentTime = audio.duration * Number($("seek").value) / 1000; });
$("rate").addEventListener("change", () => { audio.playbackRate = Number($("rate").value); });
$("follow").addEventListener("click", () => { followLyrics = !followLyrics; $("follow").textContent = `자동 스크롤 ${followLyrics ? "켬" : "끔"}`; $("follow").setAttribute("aria-pressed", String(followLyrics)); });
$("lyrics-toggle").addEventListener("click", () => $("lyrics-card").scrollIntoView({ behavior: "smooth" }));
audio.addEventListener("loadedmetadata", () => { $("duration").textContent = clock(audio.duration); });
audio.addEventListener("timeupdate", () => { $("current").textContent = clock(audio.currentTime); $("seek").value = audio.duration ? String(Math.round(audio.currentTime / audio.duration * 1000)) : "0"; syncLyrics(); });
audio.addEventListener("play", () => { $("play").textContent = "Ⅱ"; $("play").setAttribute("aria-label", "일시정지"); });
audio.addEventListener("pause", () => { $("play").textContent = "▶"; $("play").setAttribute("aria-label", "재생"); });
if ("mediaSession" in navigator) {
  navigator.mediaSession.setActionHandler("play", () => audio.play());
  navigator.mediaSession.setActionHandler("pause", () => audio.pause());
  navigator.mediaSession.setActionHandler("seekbackward", () => { audio.currentTime = Math.max(0, audio.currentTime - 10); });
  navigator.mediaSession.setActionHandler("seekforward", () => { audio.currentTime = Math.min(audio.duration || Infinity, audio.currentTime + 10); });
}
