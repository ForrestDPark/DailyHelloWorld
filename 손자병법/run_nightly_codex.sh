#!/bin/zsh
set -eu

REPO_DIR="/Users/forrestdpark/.codex-worktrees/sunzi-nightly"
SOURCE_PROMPT="/Users/forrestdpark/Desktop/PDG/DailyHelloWorld_/손자병법/nightly_codex_prompt.md"
TARGET_VERSE="${SUNZI_TARGET_VERSE:-}"
LOG_DIR="/Users/forrestdpark/Library/Logs/CodexSunzi"
LOCK_DIR="/private/tmp/com.forrest.codex-sunzi-nightly.lock"
CODEX_BIN="/opt/homebrew/bin/codex"

mkdir -p "$LOG_DIR"
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  exit 0
fi

STAMP=$(date '+%Y-%m-%d_%H-%M-%S')
LOG_FILE="$LOG_DIR/$STAMP.log"
LAST_LOG="$LOG_DIR/latest.log"

finalize_run() {
  local exit_code=$?
  rmdir "$LOCK_DIR" 2>/dev/null || true
  if [[ -f "$LOG_FILE" ]]; then
    cp "$LOG_FILE" "$LAST_LOG"
  fi
  if (( exit_code == 0 )); then
    /usr/bin/osascript -e 'display notification "야간 병법 해석을 완료했습니다. 결과 로그를 확인하세요." with title "Codex 손자병법"' >/dev/null 2>&1 || true
  else
    /usr/bin/osascript -e 'display notification "야간 병법 해석이 중단되었습니다. 실패 로그를 확인하세요." with title "Codex 손자병법"' >/dev/null 2>&1 || true
  fi
}
trap finalize_run EXIT

if [[ ! -d "$REPO_DIR/.git" ]]; then
  print -r -- "전용 저장소가 없습니다: $REPO_DIR" > "$LOG_FILE"
  exit 1
fi

cd "$REPO_DIR"
if [[ -n "$(git status --porcelain)" ]]; then
  print -r -- "이전 실행의 미완료 변경이 남아 있어 안전하게 중단합니다." > "$LOG_FILE"
  git status --short >> "$LOG_FILE"
  exit 1
fi

git fetch origin >> "$LOG_FILE" 2>&1
git merge --ff-only origin/main >> "$LOG_FILE" 2>&1

if [[ -n "$TARGET_VERSE" ]]; then
  {
    print -r -- "이번 실행은 채팅에서 소유자가 직접 승인한 九地篇 ${TARGET_VERSE}구절 전용 작업입니다. 다른 번호를 고르지 말고, Notion 원문에서 이 번호의 정확한 원문·독음을 재확인한 뒤 아래 전체 파이프라인을 수행하세요."
    /bin/cat "$SOURCE_PROMPT"
  } | /usr/bin/caffeinate -i "$CODEX_BIN" --ask-for-approval never --search exec \
    --cd "$REPO_DIR" \
    --sandbox workspace-write \
    --output-last-message "$LOG_DIR/latest-message.txt" \
    - >> "$LOG_FILE" 2>&1
else
  /usr/bin/caffeinate -i "$CODEX_BIN" --ask-for-approval never --search exec \
    --cd "$REPO_DIR" \
    --sandbox workspace-write \
    --output-last-message "$LOG_DIR/latest-message.txt" \
    - < "$SOURCE_PROMPT" >> "$LOG_FILE" 2>&1
fi
