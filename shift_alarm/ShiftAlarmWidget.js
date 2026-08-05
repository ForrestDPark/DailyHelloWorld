// ShiftAlarm 상태 위젯 (Scriptable)
//
// 같은 iCloud Documents 폴더(Scriptable 앱의 iCloud 컨테이너)의 status.json을
// 읽어 홈 화면 위젯으로 표시한다. Mac의 shift_alarm.py가 이 폴더에 자동으로
// status.json을 갱신해둔다.
//
// 홈 화면에 추가하는 법: 홈 화면 길게 눌러 편집 → "+" → Scriptable 검색 →
// 크기 선택(미디엄 권장 — 좌우 2단 레이아웃이라 스몰은 오른쪽 컬럼이 잘림) →
// 추가 → 위젯 길게 눌러 "위젯 편집" → Script를 "ShiftAlarmWidget"으로 지정.
//
// 레이아웃: 왼쪽 컬럼 = 근무/날씨/저장공간/리마인더, 오른쪽 컬럼 = 급여·AI
// 사용량(Codex/Claude). ★ 2026-08-06: 처음엔 왼쪽만 채워서 오른쪽이 비어
// 보인다는 피드백을 받아 2단 구성으로 바꿈.

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

function buildLeftColumn(stack, status) {
  const shift = status.shift;
  const shiftLabel = SHIFT_LABELS[shift] || shift || "미설정";
  const dayNum = status.shift_day_number;
  const title = dayNum ? `${shiftLabel} (${dayNum}일째)` : shiftLabel;

  addLine(stack, title, { color: COLOR_TITLE, size: 16, bold: true });
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

function buildWidget(status) {
  const widget = new ListWidget();
  widget.backgroundColor = new Color("#1c1c1e");
  widget.setPadding(14, 14, 14, 14);

  if (!status) {
    addLine(widget, "⚠️ status.json을 찾을 수 없습니다", { color: COLOR_WARN, size: 13 });
    widget.addSpacer(4);
    addLine(widget, "Mac의 shift_alarm 확인 필요", { color: COLOR_DIM, size: 11 });
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

  if (status.updated_at) {
    widget.addSpacer();
    addLine(widget, `업데이트 ${status.updated_at.replace("T", " ")}`, {
      color: new Color("#636366"),
      size: 9,
    });
  }

  return widget;
}

async function run() {
  const status = await loadStatus();
  const widget = buildWidget(status);

  if (config.runsInWidget) {
    Script.setWidget(widget);
  } else {
    await widget.presentMedium();
  }
  Script.complete();
}

await run();
