#!/bin/zsh
# macOS 단축어와 Shift Alarm이 함께 쓰는 아침 전자책 리더 진입점.
# 리더 코드를 복사하거나 덮어쓰지 않고 저장소의 단일 원본만 실행한다.

set -u

PYTHON_BIN="/opt/anaconda3/bin/python3"
PIP_BIN="/opt/anaconda3/bin/pip"
SCRIPT_DIR="${0:A:h}"
READER_SCRIPT="$SCRIPT_DIR/ebook_reader.py"
BOOK_PATH="${1:-}"

if [[ -z "$BOOK_PATH" || ! -f "$BOOK_PATH" ]]; then
  echo "사용법: $0 <책.pdf|책.epub>"
  exit 2
fi

if ! "$PYTHON_BIN" -c 'import fitz, requests, googletrans, edge_tts, ebooklib, bs4' >/dev/null 2>&1; then
  echo "📦 전자책 리더에 필요한 라이브러리를 최초 1회 설치합니다."
  "$PIP_BIN" install -r "$SCRIPT_DIR/ebook_reader_requirements.txt" || exit 1
fi

exec "$PYTHON_BIN" "$READER_SCRIPT" "$BOOK_PATH"
