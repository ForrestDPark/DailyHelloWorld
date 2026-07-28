#!/bin/zsh
# 일본어 영상 → 자막(Whisper) + 번역(구글) + 후리가나 + 노션 기록 + 메모 앱 + MD + EPUB
# 사용법: ./whisper_series_stream.sh [영상 폴더 경로]  (생략하면 현재 폴더)
#
# 필요 시크릿(macOS 키체인, 평문 하드코딩 금지):
#   security add-generic-password -a "$USER" -s "jp_subtitle_notion_token" -w "<노션 통합 토큰>" -U
# 대표 이미지는 외부 이미지 호스팅 없이 Notion File Upload API로 직접 저장한다.

TARGET_DIR="${1:-.}"
TARGET_PATH=$(cd "$TARGET_DIR" && pwd)
TEMP_SCRIPT="$HOME/whisper_series_stream_run.sh"
# 이 스크립트 자신의 폴더 — 같은 폴더의 extract_high_pitch_video.py를 부르기 위함.
SCRIPT_DIR="$(cd "$(dirname "${(%):-%x}")" && pwd)"
# 운동용 영상 배경음 mp3가 있는 로컬 폴더(저작권 있는 음원이라 git에는 안 올림 — README 참조).
BGM_DIR="${BGM_DIR:-/Users/forrestdpark/Desktop/BlogImage/BGM_DIR}"
# 운동용 영상 목표 길이(분) — 메뉴바 앱에서 입력받아 넘겨줌. 비어있으면 extract_high_pitch_video.py의
# 기존 방식(상위 35% 고정 기준)을 그대로 쓴다.
TARGET_MINUTES="${TARGET_MINUTES:-}"
# 고음 구간 앞뒤에 포함할 영상 여유(초) — 메뉴바 키패드에서 입력.
HIGHLIGHT_PAD="${HIGHLIGHT_PAD:-1}"

/opt/anaconda3/bin/python3 -m pip install requests pykakasi librosa soundfile --quiet --disable-pip-version-check 2>/dev/null

cat << 'EOF' > "$TEMP_SCRIPT"
#!/bin/zsh
export PATH="/opt/homebrew/bin:/usr/local/bin:/opt/anaconda3/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"

cd "$WORKING_DIR"
echo "=================================================="
echo "📂 작업 경로: $WORKING_DIR"
echo "🎵 [영상 길이별 자동 분할 + 통합 자막 + 메모 앱 + MD + EPUB] 엔진 가동"
echo "=================================================="

# ── /tmp 여유 공간 확보 ───────────────────────────────────────────
rm -f /tmp/ls_* 2>/dev/null
MYTMP="${TMPDIR:-$HOME/.ls_tmp}"
mkdir -p "$MYTMP"

MODEL_PATH="/opt/homebrew/share/whisper-cpp/models/ggml-medium.bin"
[[ ! -f "$MODEL_PATH" ]] && MODEL_PATH="/opt/homebrew/share/whisper-cpp/models/ggml-small.bin"

WHISPER_EXE="/opt/homebrew/bin/whisper-cli"
CORRECTIONS_FILE="${SCRIPT_DIR}/whisper_corrections.txt"
WHISPER_PROMPT="일본어, 대사, 한자, 후리가나"
if [[ -f "$CORRECTIONS_FILE" ]]; then
    CONFIRMED_TERMS=$(sed -E 's/#.*$//; /^[[:space:]]*$/d' "$CORRECTIONS_FILE" \
        | head -80 | paste -sd '、' -)
    [[ -n "$CONFIRMED_TERMS" ]] && WHISPER_PROMPT="${WHISPER_PROMPT}。確認済み語彙：${CONFIRMED_TERMS}"
fi
# 재추출 시 현재 "_운동용" 결과와 예전 "_고음영상" 결과가 원본인 척 다시
# 처리되지 않도록 둘 다 제외한다.
VALID_FILES=(*.(mp4|webm|mkv|mov)(N))
VALID_FILES=(${VALID_FILES:#*_운동용*})
VALID_FILES=(${VALID_FILES:#*_고음영상*})

if [[ ${#VALID_FILES[@]} -eq 0 ]]; then
    echo "⚠️  처리할 영상 파일이 없습니다."
    exit 0
fi

echo "📋 발견된 영상 ${#VALID_FILES[@]}개: ${VALID_FILES[@]}"

# ── 1단계: 발견된 모든 원본의 운동용 영상부터 추출 ─────────────────
# 파일 하나의 자막·Notion·EPUB까지 전부 끝낸 뒤 다음 파일로 넘어가면
# 뒤쪽 영상의 운동용 결과를 오래 기다려야 한다. 시작 시점에 발견한 원본을
# 먼저 전부 순회하고, 한 파일이 실패해도 나머지 고음 추출은 계속한다.
echo "\n\033[1;36m==================================================\033[0m"
echo "\033[1;36m🎧 1단계: 모든 원본의 운동용 영상(+배경음) 우선 추출\033[0m"
echo "\033[1;36m==================================================\033[0m"

HIGHLIGHT_FAILED=()
HIGHLIGHT_INDEX=0
for HIGHLIGHT_FILE in "${VALID_FILES[@]}"; do
    HIGHLIGHT_INDEX=$(( HIGHLIGHT_INDEX + 1 ))
    echo "\n--------------------------------------------------"
    echo "🎬 [${HIGHLIGHT_INDEX}/${#VALID_FILES[@]}] $HIGHLIGHT_FILE"
    echo "--------------------------------------------------"

    PITCH_ARGS=(--bgm-dir "$BGM_DIR" --bgm-volume 0.28 --pad "$HIGHLIGHT_PAD")
    if [[ -n "$TARGET_MINUTES" ]]; then
        PITCH_ARGS+=(--target-minutes "$TARGET_MINUTES")
        echo "🎯 운동용 영상 목표 길이: ${TARGET_MINUTES}분"
    fi
    echo "↔️ 고음 구간 앞뒤 여유: ${HIGHLIGHT_PAD}초"

    if /opt/anaconda3/bin/python3 "${SCRIPT_DIR}/extract_high_pitch_video.py" \
        "$HIGHLIGHT_FILE" "${PITCH_ARGS[@]}"; then
        echo "✅ [${HIGHLIGHT_INDEX}/${#VALID_FILES[@]}] 운동용 영상 추출 완료"
    else
        echo "⚠️  [${HIGHLIGHT_INDEX}/${#VALID_FILES[@]}] 운동용 영상 추출 실패 — 다음 원본을 계속합니다."
        HIGHLIGHT_FAILED+=("$HIGHLIGHT_FILE")
    fi
done

echo "\n✅ 1단계 완료: ${#VALID_FILES[@]}개 원본의 운동용 영상 추출 시도 완료"
if [[ ${#HIGHLIGHT_FAILED[@]} -gt 0 ]]; then
    echo "⚠️  운동용 영상 추출 실패 ${#HIGHLIGHT_FAILED[@]}개: ${HIGHLIGHT_FAILED[@]}"
fi
echo "\n\033[1;35m==================================================\033[0m"
echo "\033[1;35m📝 2단계: 자막·번역·Notion·EPUB 순차 처리 시작\033[0m"
echo "\033[1;35m==================================================\033[0m"

# ── 2단계는 subtitle_pipeline_body.sh와 subtitle_notion_epub_only.sh(단독 실행)가
#   똑같이 공유하는 로직이라 여기서는 그 파일을 그대로 불러 쓴다(중복 유지 방지).
export WORKING_DIR="$WORKING_DIR"
export SCRIPT_DIR="$SCRIPT_DIR"
source "${SCRIPT_DIR}/subtitle_pipeline_body.sh"
exit 0

EOF

chmod +x "$TEMP_SCRIPT"

# ── 새 iTerm 창에서 실행 ────────────────────────────────────────────
# ★ 2026-07-23: 원래 iTerm을 `tell application "iTerm" ...`으로 제어했는데,
#   이건 macOS 자동화(Automation) 권한이 필요하고, 이 스크립트가 메뉴바 앱
#   (launchd 백그라운드 프로세스) 등에서 호출되면 권한 팝업 자체가 안 떠서
#   조용히 실패한다 (shift_alarm 프로젝트의 이북리더에서 겪은 것과 동일한
#   문제 — 그쪽 README 8-1 참조). 대신 실행 가능한 .command 파일을 만들고
#   `open`으로 여는 방식으로 바꿨다 — 권한이 전혀 필요 없다.
#   `open -a iTerm <파일>.command`는 AppleEvent가 아니라 Launch Services를
#   사용하므로 자동화 권한 없이 실행된다. 장면 이미지/TTS 모니터링은 제거됐지만,
#   긴 처리 로그를 기존 사용 환경과 동일하게 보여주기 위해 iTerm은 유지한다.
LAUNCHER="/tmp/_whisper_series_launch.command"
cat > "$LAUNCHER" <<LAUNCHEREOF
#!/bin/zsh
export WORKING_DIR='$TARGET_PATH'
export SCRIPT_DIR='$SCRIPT_DIR'
export BGM_DIR='$BGM_DIR'
export TARGET_MINUTES='$TARGET_MINUTES'
export HIGHLIGHT_PAD='$HIGHLIGHT_PAD'
zsh "$TEMP_SCRIPT"
rm -f "$TEMP_SCRIPT"
LAUNCHEREOF
chmod +x "$LAUNCHER"
open -a iTerm "$LAUNCHER"
