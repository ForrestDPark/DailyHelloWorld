const cards = document.getElementById("cards");
const statusText = document.getElementById("status");
const refreshButton = document.getElementById("refresh");

const esc = (value = "") => String(value).replace(/[&<>'"]/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[char]));
const safeUrl = (value) => /^https:\/\//i.test(value || "") ? value : "#";

function formatTime(value) {
  if (!value) return "업데이트 시각 없음";
  return new Intl.DateTimeFormat("ko-KR", {dateStyle:"medium", timeStyle:"short"}).format(new Date(value));
}

function renderCard(item, type) {
  const isCareer = type === "career";
  if (!item) return `<article class="job-card empty-card"><p class="tag">${isCareer ? "커리어" : "파트타임"}</p><h3>추천을 준비하고 있어요</h3><p>다음 수집이 끝나면 이곳에 표시됩니다.</p></article>`;
  const score = Number(item.score || 0);
  return `<article class="job-card ${isCareer ? "career" : "parttime"}">
    <div class="job-top"><p class="tag">${isCareer ? "커리어 추천" : "파트타임 추천"}</p><span class="score"><b>${score}</b>/100</span></div>
    <p class="company">${esc(item.company || "회사 미상")}</p><h3>${esc(item.title || "공고 제목 없음")}</h3>
    <div class="meta"><span>${esc(item.source || "출처 미상")}</span><span>${esc(formatTime(item.updated_at))}</span></div>
    <div class="actions"><a href="${safeUrl(item.job_url)}" target="_blank" rel="noreferrer">공고 원문</a><a class="primary" href="${safeUrl(item.url)}" target="_blank" rel="noreferrer">분석 보기</a></div>
  </article>`;
}

async function load() {
  refreshButton.disabled = true;
  statusText.textContent = "추천 데이터를 불러오는 중이에요";
  try {
    const response = await fetch("/api/career-summary", {credentials:"same-origin"});
    if (response.status === 401) { location.href = "/"; return; }
    if (response.status === 403) throw new Error("이직 준비실은 관리자 계정에서만 볼 수 있어요.");
    if (!response.ok) throw new Error("추천 데이터를 불러오지 못했어요.");
    const data = await response.json();
    cards.innerHTML = renderCard(data.career, "career") + renderCard(data.parttime, "parttime");
    statusText.textContent = "최신 추천을 불러왔어요";
  } catch (error) {
    cards.innerHTML = `<article class="job-card error-card"><p class="tag">연결 확인</p><h3>${esc(error.message)}</h3><p>잠시 뒤 새로고침해 주세요.</p></article>`;
    statusText.textContent = "데이터 연결을 확인해 주세요";
  } finally { refreshButton.disabled = false; }
}

refreshButton.addEventListener("click", load);
load();
