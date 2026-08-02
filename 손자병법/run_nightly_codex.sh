#!/bin/zsh
set -eu

REPO_DIR="/Users/forrestdpark/.codex-worktrees/sunzi-nightly"
SOURCE_PROMPT="/Users/forrestdpark/Desktop/PDG/DailyHelloWorld_/손자병법/nightly_codex_prompt.md"
LOG_DIR="/Users/forrestdpark/Library/Logs/CodexSunzi"
LOCK_DIR="/private/tmp/com.forrest.codex-sunzi-nightly.lock"
CODEX_BIN="/opt/homebrew/bin/codex"

mkdir -p "$LOG_DIR"
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  exit 0
fi
trap 'rmdir "$LOCK_DIR" 2>/dev/null || true' EXIT

STAMP=$(date '+%Y-%m-%d_%H-%M-%S')
LOG_FILE="$LOG_DIR/$STAMP.log"
LAST_LOG="$LOG_DIR/latest.log"

if [[ ! -d "$REPO_DIR/.git" ]]; then
  print -r -- "전용 저장소가 없습니다: $REPO_DIR" > "$LOG_FILE"
  cp "$LOG_FILE" "$LAST_LOG"
  exit 1
fi

cd "$REPO_DIR"
if [[ -n "$(git status --porcelain)" ]]; then
  print -r -- "이전 실행의 미완료 변경이 남아 있어 안전하게 중단합니다." > "$LOG_FILE"
  git status --short >> "$LOG_FILE"
  cp "$LOG_FILE" "$LAST_LOG"
  exit 1
fi

git fetch origin >> "$LOG_FILE" 2>&1
git merge --ff-only origin/main >> "$LOG_FILE" 2>&1

/usr/bin/caffeinate -i "$CODEX_BIN" exec \
  --cd "$REPO_DIR" \
  --sandbox workspace-write \
  --ask-for-approval never \
  --search \
  --output-last-message "$LOG_DIR/latest-message.txt" \
  - < "$SOURCE_PROMPT" >> "$LOG_FILE" 2>&1

cp "$LOG_FILE" "$LAST_LOG"
