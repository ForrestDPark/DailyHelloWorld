#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="${0:A:h}"
REPO_DIR="${SCRIPT_DIR:h}"

cd "$SCRIPT_DIR"
python3 -m unittest -v test_job_collector.py
python3 -m py_compile job_collector.py

cd "$REPO_DIR"
git diff --check -- README.md "이직시스템"

if git ls-files "이직시스템/config.json" "이직시스템/data" "이직시스템/exports" | grep -q .; then
  echo "❌ 개인 설정이나 수집 데이터가 Git 추적 중입니다."
  exit 1
fi

if git diff --cached -- "이직시스템" README.md | grep -E 'SARAMIN_ACCESS_KEY\s*=\s*[A-Za-z0-9_-]{16,}|access-key["'"'"']?\s*[:=]\s*["'"'"'][A-Za-z0-9_-]{16,}' >/dev/null; then
  echo "❌ stage된 변경에 API 키로 보이는 값이 있습니다."
  exit 1
fi

echo "✅ 이직시스템 동기화 전 검증 완료"
