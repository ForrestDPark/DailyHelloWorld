#!/bin/zsh
# 운동용 고음 영상 추출 없이, 자막(Whisper) + 번역 + 후리가나 + 노션 기록 + 메모 앱
# + MD + EPUB 단계만 단독으로 실행한다. 실제 로직은 subtitle_pipeline_body.sh에
# 있고, 이 스크립트는 그 파일을 위한 인자 파싱 + 새 iTerm 창 실행 래퍼일 뿐이다.
# 사용법: ./subtitle_notion_epub_only.sh [영상 폴더 경로]  (생략하면 현재 폴더)
#
# 필요 시크릿(macOS 키체인, 평문 하드코딩 금지):
#   security add-generic-password -a "$USER" -s "jp_subtitle_notion_token" -w "<노션 통합 토큰>" -U

TARGET_DIR="${1:-.}"
TARGET_PATH=$(cd "$TARGET_DIR" && pwd)
# 이 스크립트 자신의 폴더 — 같은 폴더의 subtitle_pipeline_body.sh를 부르기 위함.
SCRIPT_DIR="$(cd "$(dirname "${(%):-%x}")" && pwd)"
# ★ 2026-08-29: whisper_series_stream.sh와 같은 이유로 완료 마커용 실행 ID.
JP_SUBTITLE_RUN_ID="${JP_SUBTITLE_RUN_ID:-}"

/opt/anaconda3/bin/python3 -m pip install requests pykakasi --quiet --disable-pip-version-check 2>/dev/null

# ── 새 iTerm 창에서 실행 ────────────────────────────────────────────
# whisper_series_stream.sh와 동일한 이유로 `open -a iTerm <파일>.command` 방식을
# 쓴다 — AppleEvent가 아니라 Launch Services를 쓰므로 자동화 권한이 필요 없다.
LAUNCHER="/tmp/_subtitle_notion_epub_only_launch.command"
cat > "$LAUNCHER" <<LAUNCHEREOF
#!/bin/zsh
export WORKING_DIR='$TARGET_PATH'
export SCRIPT_DIR='$SCRIPT_DIR'
export WORKOUT_EXTRACTION_ENABLED=0
zsh "${SCRIPT_DIR}/subtitle_pipeline_body.sh"
if [[ -n '$JP_SUBTITLE_RUN_ID' ]]; then
  echo done > "/tmp/_jp_subtitle_run_$JP_SUBTITLE_RUN_ID.done"
fi
LAUNCHEREOF
chmod +x "$LAUNCHER"
open -a iTerm "$LAUNCHER"
