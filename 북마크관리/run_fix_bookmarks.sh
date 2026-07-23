#!/bin/bash
# fix_bookmarks.py 실행 래퍼 — --apply가 있을 때만 크롬을 자동으로 껐다 켠다.
# 사용법은 fix_bookmarks.py와 동일하게 인자를 그대로 넘기면 됨. 예:
#   ./run_fix_bookmarks.sh --all --replace "kr43" "kr44" --apply

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHROME_MATCH="Google Chrome$"

needs_apply=false
for arg in "$@"; do
  if [ "$arg" = "--apply" ]; then
    needs_apply=true
  fi
done

chrome_was_running=false
if pgrep -f "$CHROME_MATCH" >/dev/null; then
  chrome_was_running=true
fi

if [ "$needs_apply" = true ] && [ "$chrome_was_running" = true ]; then
  echo "크롬 종료 중..."
  osascript -e 'quit app "Google Chrome"'
  for i in 1 2 3 4 5 6 7 8 9 10; do
    pgrep -f "$CHROME_MATCH" >/dev/null || break
    sleep 1
  done
  if pgrep -f "$CHROME_MATCH" >/dev/null; then
    echo "크롬이 10초 안에 종료되지 않았습니다. 수동으로 종료 후 다시 실행하세요." >&2
    exit 1
  fi
  echo "크롬 종료 확인됨."
fi

python3 "$SCRIPT_DIR/fix_bookmarks.py" "$@"
status=$?

if [ "$needs_apply" = true ] && [ "$chrome_was_running" = true ]; then
  echo "크롬 다시 여는 중..."
  open -a "Google Chrome"
fi

exit $status
