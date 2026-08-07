// Variables used by Scriptable.
// These must be at the very top of the file. Do not edit.
// icon-color: brown; icon-glyph: magic;
// ShiftAlarm 상태 위젯 (Scriptable)
//
// 같은 iCloud Documents 폴더(Scriptable 앱의 iCloud 컨테이너)의 status.json을
// 읽어 홈 화면 위젯으로 표시한다. Mac의 shift_alarm.py가 이 폴더에 자동으로
// status.json을 갱신해둔다.
//
// 홈 화면에 추가하는 법: 홈 화면 길게 눌러 편집 → "+" → Scriptable 검색 →
// 크기 선택 → 추가 → 위젯 길게 눌러 "위젯 편집" → Script를 "ShiftAlarmWidget"
// 으로 지정.
//
// 크기별 레이아웃(★ 2026-08-06, config.widgetFamily로 분기):
//   small  — 근무·며칠째·날씨만 (한 줄, 잘리지 않게 최소한만)
//   medium — 왼쪽(근무·날씨·저장공간·리마인더) / 오른쪽(급여·AI 사용량) 2단
//   large  — medium 레이아웃 + 아래에 손자병법 최신 구절 + 이직시스템 요약 추가
// medium/small에 손자병법·이직시스템까지 욱여넣으면 위젯 프레임을 넘어가서
// 잘리므로(Scriptable은 내용을 자동으로 줄여주지 않음) large 전용으로 뺐다.

const fm = FileManager.iCloud();
const statusPath = fm.joinPath(fm.documentsDirectory(), "status.json");

const SHIFT_LABELS = {
  Day: "☀️ 주간",
  Swing: "🌇 오후",
  GY: "🌙 야간",
  휴무: "🛌 휴무",
};

const MAX_REMINDERS_SHOWN = 3;

const COLOR_TITLE = new Color("#5ac8fa");
const COLOR_TEXT = Color.white();
const COLOR_DIM = new Color("#8e8e93");
const COLOR_SUB = new Color("#d1d1d6");
const COLOR_WARN = new Color("#ff6961");
const COLOR_GREEN = new Color("#34c759");
const COLOR_ORANGE = new Color("#ff9f0a");
const COLOR_PURPLE = new Color("#bf5af2");

async function loadStatus() {
  if (!fm.fileExists(statusPath)) return null;
  try {
    if (!fm.isFileDownloaded(statusPath)) {
      await fm.downloadFileFromiCloud(statusPath);
    }
    const raw = fm.readString(statusPath);
    return JSON.parse(raw);
  } catch (e) {
    return null;
  }
}

function addLine(stack, text, { color = COLOR_TEXT, size = 12, bold = false, lineLimit = 1 } = {}) {
  const t = stack.addText(text);
  t.textColor = color;
  t.font = bold ? Font.boldSystemFont(size) : Font.systemFont(size);
  t.lineLimit = lineLimit;
  return t;
}

function shiftTitle(status) {
  const shiftLabel = SHIFT_LABELS[status.shift] || status.shift || "미설정";
  const dayNum = status.shift_day_number;
  return dayNum ? `${shiftLabel} (${dayNum}일째)` : shiftLabel;
}

function buildLeftColumn(stack, status) {
  addLine(stack, shiftTitle(status), { color: COLOR_TITLE, size: 16, bold: true });
  stack.addSpacer(6);

  if (status.weather) {
    addLine(stack, `🌤 ${status.weather}`, { size: 12 });
    stack.addSpacer(3);
  }

  if (status.storage_free_gb !== null && status.storage_free_gb !== undefined) {
    const low = status.storage_free_gb <= 5;
    addLine(stack, `💾 저장공간 ${status.storage_free_gb}GB`, {
      color: low ? COLOR_WARN : COLOR_TEXT,
    });
    stack.addSpacer(6);
  }

  const reminders = status.reminders || [];
  if (reminders.length > 0) {
    addLine(stack, "🔔 오늘의 리마인더", { color: COLOR_DIM, size: 11, bold: true });
    stack.addSpacer(3);
    reminders.slice(0, MAX_REMINDERS_SHOWN).forEach((r) => {
      addLine(stack, `· ${r}`, { color: COLOR_SUB, size: 11 });
      stack.addSpacer(2);
    });
    const remaining = reminders.length - MAX_REMINDERS_SHOWN;
    if (remaining > 0) {
      addLine(stack, `외 ${remaining}건`, { color: COLOR_DIM, size: 10 });
    }
  } else {
    addLine(stack, "🔔 오늘 리마인더 없음", { color: COLOR_DIM, size: 11 });
  }
}

function buildRightColumn(stack, status) {
  addLine(stack, "오늘", { color: COLOR_DIM, size: 11, bold: true });
  stack.addSpacer(3);
  if (status.earnings_short) {
    addLine(stack, status.earnings_short, { size: 12, lineLimit: 2 });
  } else {
    addLine(stack, "💰 -", { color: COLOR_DIM, size: 12 });
  }
  stack.addSpacer(10);

  addLine(stack, "🪙 AI 사용량", { color: COLOR_DIM, size: 11, bold: true });
  stack.addSpacer(3);

  if (status.codex_percent !== null && status.codex_percent !== undefined) {
    const color = status.codex_critical ? COLOR_WARN : COLOR_GREEN;
    addLine(stack, `Codex ${Math.round(status.codex_percent)}%`, { color, size: 12 });
  } else {
    addLine(stack, "Codex -", { color: COLOR_DIM, size: 12 });
  }
  stack.addSpacer(2);

  if (status.claude_percent !== null && status.claude_percent !== undefined) {
    const color = status.claude_critical ? COLOR_WARN : COLOR_ORANGE;
    addLine(stack, `Claude ${Math.round(status.claude_percent)}%`, { color, size: 12 });
  } else {
    addLine(stack, "Claude -", { color: COLOR_DIM, size: 12 });
  }
}

function buildBottomSection(widget, status) {
  widget.addSpacer(10);

  if (status.sunzi_title) {
    addLine(widget, `⚔️ 손자병법 최신`, { color: COLOR_DIM, size: 11, bold: true });
    widget.addSpacer(2);
    addLine(widget, status.sunzi_title, { color: COLOR_PURPLE, size: 12, lineLimit: 2 });
    widget.addSpacer(8);
  }

  if (status.job_company) {
    const scoreText = status.job_score !== null && status.job_score !== undefined
      ? `🎯 [${status.job_score}점] 오늘의 추천 공고`
      : `🎯 오늘의 추천 공고`;
    addLine(widget, scoreText, { color: COLOR_DIM, size: 11, bold: true });
    widget.addSpacer(2);
    const jobLabel = `${status.job_company} — ${status.job_title || ""}`;
    const jobLine = addLine(widget, jobLabel, { color: COLOR_SUB, size: 12, lineLimit: 2 });
    if (status.job_url) jobLine.url = status.job_url;
    if (status.job_notion_url) {
      widget.addSpacer(2);
      const notionLine = addLine(widget, "📄 AI 분석 보기", { color: COLOR_PURPLE, size: 11 });
      notionLine.url = status.job_notion_url;
    }
  }

  // ★ 2026-08-07: 공고 섹션과 형식은 맞추되, 라지 위젯 프레임이 이미 꽉 찬
  // 편이라(손자병법+공고 3줄) 한 줄로 압축했다 — 넘치면 사용자가 알려주면 조정.
  if (status.contest_organizer) {
    widget.addSpacer(8);
    const scoreText = status.contest_score !== null && status.contest_score !== undefined
      ? `🏆 [${status.contest_score}점] `
      : `🏆 `;
    const contestLabel = `${scoreText}${status.contest_organizer} — ${status.contest_title || ""}`;
    const contestLine = addLine(widget, contestLabel, { color: COLOR_SUB, size: 11, lineLimit: 2 });
    if (status.contest_url) contestLine.url = status.contest_url;
  }
}

function buildSmall(widget, status) {
  addLine(widget, shiftTitle(status), { color: COLOR_TITLE, size: 16, bold: true });
  widget.addSpacer(6);
  if (status.weather) {
    addLine(widget, `🌤 ${status.weather}`, { size: 12 });
  }
}

function buildWidget(status, family) {
  const widget = new ListWidget();
  widget.backgroundColor = new Color("#1c1c1e");
  widget.setPadding(14, 14, 14, 14);

  if (!status) {
    addLine(widget, "⚠️ status.json을 찾을 수 없습니다", { color: COLOR_WARN, size: 13 });
    widget.addSpacer(4);
    addLine(widget, "Mac의 shift_alarm 확인 필요", { color: COLOR_DIM, size: 11 });
    return widget;
  }

  if (family === "small") {
    buildSmall(widget, status);
    return widget;
  }

  const row = widget.addStack();
  row.layoutHorizontally();

  const left = row.addStack();
  left.layoutVertically();
  buildLeftColumn(left, status);

  row.addSpacer(14);

  const right = row.addStack();
  right.layoutVertically();
  buildRightColumn(right, status);

  if (family === "large") {
    buildBottomSection(widget, status);
  }

  widget.addSpacer();
  if (status.updated_at) {
    addLine(widget, `업데이트 ${status.updated_at.replace("T", " ")}`, {
      color: new Color("#636366"),
      size: 9,
    });
  }

  return widget;
}

async function run() {
  const status = await loadStatus();
  const family = config.widgetFamily || "large"; // 앱 안에서 미리보기 실행할 땐 large로 가정
  const widget = buildWidget(status, family);

  if (config.runsInWidget) {
    Script.setWidget(widget);
  } else if (family === "small") {
    await widget.presentSmall();
  } else if (family === "medium") {
    await widget.presentMedium();
  } else {
    await widget.presentLarge();
  }
  Script.complete();
}

await run();
