#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="${0:A:h}"
REPO_DIR="${SCRIPT_DIR:h}"
cd "$SCRIPT_DIR"
python3 -m unittest -v test_contest_tracker.py
python3 -m py_compile contest_tracker.py
cd "$REPO_DIR"
git diff --check -- README.md "경진대회시스템"
if git ls-files "경진대회시스템/data" "경진대회시스템/exports" "경진대회시스템/config.json" | grep -q .; then
  echo "❌ 개인 설정이나 수집 데이터가 Git 추적 중입니다."
  exit 1
fi
echo "✅ 경진대회시스템 동기화 전 검증 완료"
