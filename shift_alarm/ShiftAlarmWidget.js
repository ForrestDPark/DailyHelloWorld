// ShiftAlarm 상태 위젯 (Scriptable)
//
// 같은 iCloud Documents 폴더(Scriptable 앱의 iCloud 컨테이너)의 status.json을
// 읽어 홈 화면 위젯으로 표시한다. Mac의 shift_alarm.py가 이 폴더에 자동으로
// status.json을 갱신해둔다.
//
// 홈 화면에 추가하는 법: 홈 화면 길게 눌러 편집 → "+" → Scriptable 검색 →
// 크기 선택(미디엄 권장) → 추가 → 위젯 길게 눌러 "위젯 편집" → Script를
// "ShiftAlarmWidget"으로 지정.

const fm = FileManager.iCloud();
const statusPath = fm.joinPath(fm.documentsDirectory(), "status.json");

const SHIFT_LABELS = {
  Day: "☀️ 주간",
  Swing: "🌇 오후",
  GY: "🌙 야간",
  휴무: "🛌 휴무",
};

const MAX_REMINDERS_SHOWN = 3;

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

function addLine(widget, text, { color = Color.white(), size = 12, bold = false, lineLimit = 1 } = {}) {
  const t = widget.addText(text);
  t.textColor = color;
  t.font = bold ? Font.boldSystemFont(size) : Font.systemFont(size);
  t.lineLimit = lineLimit;
  return t;
}

function buildWidget(status) {
  const widget = new ListWidget();
  widget.backgroundColor = new Color("#1c1c1e");
  widget.setPadding(14, 14, 14, 14);

  if (!status) {
    addLine(widget, "⚠️ status.json을 찾을 수 없습니다", { color: new Color("#ff6961"), size: 13 });
    widget.addSpacer(4);
    addLine(widget, "Mac의 shift_alarm 확인 필요", { color: new Color("#8e8e93"), size: 11 });
    return widget;
  }

  const shift = status.shift;
  const shiftLabel = SHIFT_LABELS[shift] || shift || "미설정";
  const dayNum = status.shift_day_number;
  const title = dayNum ? `${shiftLabel} (${dayNum}일째)` : shiftLabel;

  addLine(widget, title, { color: new Color("#5ac8fa"), size: 16, bold: true });
  widget.addSpacer(6);

  if (status.weather) {
    addLine(widget, `🌤 ${status.weather}`, { size: 12 });
    widget.addSpacer(3);
  }

  if (status.storage_free_gb !== null && status.storage_free_gb !== undefined) {
    const low = status.storage_free_gb <= 5;
    addLine(widget, `💾 저장공간 ${status.storage_free_gb}GB`, {
      color: low ? new Color("#ff6961") : Color.white(),
      size: 12,
    });
    widget.addSpacer(6);
  }

  const reminders = status.reminders || [];
  if (reminders.length > 0) {
    addLine(widget, "🔔 오늘의 리마인더", { color: new Color("#8e8e93"), size: 11, bold: true });
    widget.addSpacer(3);
    reminders.slice(0, MAX_REMINDERS_SHOWN).forEach((r) => {
      addLine(widget, `· ${r}`, { color: new Color("#d1d1d6"), size: 11 });
      widget.addSpacer(2);
    });
    const remaining = reminders.length - MAX_REMINDERS_SHOWN;
    if (remaining > 0) {
      addLine(widget, `외 ${remaining}건`, { color: new Color("#8e8e93"), size: 10 });
    }
  } else {
    addLine(widget, "🔔 오늘 리마인더 없음", { color: new Color("#8e8e93"), size: 11 });
  }

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
