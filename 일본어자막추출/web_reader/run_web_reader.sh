#!/bin/zsh
set -euo pipefail
SCRIPT_DIR="${0:A:h}"
if [[ -z "${JP_WEB_READER_PASSWORD:-}" ]]; then
  echo "JP_WEB_READER_PASSWORD를 8자 이상으로 설정해 주세요."
  echo "예: JP_WEB_READER_PASSWORD='원하는비밀번호' $0"
  exit 1
fi
exec /usr/bin/env python3 "$SCRIPT_DIR/server.py" "$@"
