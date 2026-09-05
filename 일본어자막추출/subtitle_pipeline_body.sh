#!/bin/zsh
# 자막(Whisper) + 번역(구글) + 후리가나 + 노션 기록 + 메모 앱 + MD + EPUB 파이프라인 본체.
# whisper_series_stream.sh(운동용 영상까지 연달아 실행)와
# subtitle_notion_epub_only.sh(이 단계만 단독 실행) 둘 다 이 파일을 그대로 불러 쓴다.
# 로직을 두 곳에 복사해두면 한쪽만 고치고 잊어버리는 문제가 생기므로 파일 하나로 합침.
#
# 호출자가 미리 export해야 하는 값: WORKING_DIR, SCRIPT_DIR
# WORKOUT_EXTRACTION_ENABLED: 이번 실행에 운동용 고음 영상 추출 단계가 있었는지.
# whisper_series_stream.sh=1, subtitle_notion_epub_only.sh=0. 미지정(단독 테스트
# 등)이면 안전하게 "있었다"고 가정해 기존 avMusic 확인 절차를 그대로 요구한다.
WORKOUT_EXTRACTION_ENABLED="${WORKOUT_EXTRACTION_ENABLED:-1}"

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

# ★★★ 2026-07-28: whisper.cpp 내장 VAD(Silero) — 껐다가 다시 켰다. 실제 영상
# (SONE-486)에서 긴 무음/신음 구간 직전 대사의 "종료" 시각이 다음 발화 시작
# 지점까지 늘어나는 버그를 발견해서(예: "いいなぁ" 한 마디가 740초짜리로 기록)
# 한 번 껐었는데, 확인해보니 이 파이프라인의 실제 산출물(EPUB/Notion/메모앱/
# 장면 대표 이미지)은 전부 "시작" 시각만 쓰거나 타임스탬프를 아예 안 쓴다
# (finalize_japanese_book.py·sync_book_to_notion.py에 start/end 참조 없음,
# capture_representative_image도 start만 사용) — 깨지는 건 "종료" 시각뿐이라
# 실사용에 전혀 영향이 없다는 걸 사용자가 확인해줘서 다시 켰다. 유일한 영향은
# 통합 SRT(<파일명>.srt)를 실제 영상 자막으로 재생할 때 그 줄들이 너무 오래
# 떠 있는 것뿐 — 이 프로젝트는 그 SRT를 자막 재생용이 아니라 EPUB 대사 추출
# 원본으로만 쓰므로 무시해도 된다.
VAD_MODEL_PATH="/opt/homebrew/share/whisper-cpp/models/ggml-silero-v5.1.2.bin"
if [[ ! -f "$VAD_MODEL_PATH" ]]; then
    echo "⬇️  VAD 모델(Silero) 없음 — 다운로드 중..."
    curl -sL --output "$VAD_MODEL_PATH" \
        "https://huggingface.co/ggml-org/whisper-vad/resolve/main/ggml-silero-v5.1.2.bin"
    [[ ! -s "$VAD_MODEL_PATH" ]] && rm -f "$VAD_MODEL_PATH"
fi
VAD_ARGS=()
if [[ -f "$VAD_MODEL_PATH" ]]; then
    VAD_ARGS=(--vad --vad-model "$VAD_MODEL_PATH")
else
    echo "⚠️  VAD 모델을 준비하지 못해 무음/비음성 구간 없이 전체 오디오를 처리합니다."
fi

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

ATTEMPTED_FILES=()
COMPLETED_COUNT=0

# ── 학습카드 누락 회차 자동 복구 ──────────────────────────────────
# ★ 2026-09-04: "만약에 epub 에서 학습카드가 없는경우에는 학습카드를
# 다시 만들도록 파이프라인 수정하면 좋겠어" 요청 — 새 영상을 처리하기
# 전에 매번, library/<제목>/ 폴더 중 대사 원재료(transcript_part*.jsonl)는
# 남아 있는데 scene_study_cards.json이 없거나 비어 있는(예전 실행에서
# generate_summary.py가 쿼터 소진 등으로 실패했던) 회차를 찾아 재시도한다.
# 대사 원재료조차 없는 회차(정리 단계에서 이미 삭제됨 — 위 SUMMARY_OK 수정
# 이전에 처리된 것들)는 여기서 되살릴 수 없으니 건너뛴다(원본 영상부터
# 재추출해야 함).
echo "\n\033[1;36m==================================================\033[0m"
echo "\033[1;36m🩹 학습카드 누락 회차 자동 복구 확인 중...\033[0m"
echo "\033[1;36m==================================================\033[0m"
LIBRARY_DIR="${SCRIPT_DIR}/library"
COMPLETED_EPUB_DIR_FOR_BACKFILL="/Users/forrestdpark/Desktop/BlogImage/av완성작"

# ★ 2026-09-05: "라이브러리가 없으면 여기서(av완성작) 보충해" 요청 — 위 SUMMARY_OK
# 수정 이전에 이미 library/<작품명>/이 통째로 지워진 회차는 원본 영상 없이는 복구
# 불가능하다고 판단했었는데, 낭독판 EPUB 자체가 전체 대사(ja/ko/후리가나)를 페이지마다
# 그대로 담고 있어서 원본 영상 없이도 여기서 다시 뽑아낼 수 있다
# (recover_study_cards_from_epub.py, 2026-09-05). av완성작의 낭독판 중 library에
# 대응 폴더가 없는 것을 찾아 먼저 대사 원재료부터 복구한 뒤, 아래 기존 재시도
# 루프가 학습카드까지 이어서 만든다.
if [[ -d "$COMPLETED_EPUB_DIR_FOR_BACKFILL" ]]; then
    for OLD_EPUB in "$COMPLETED_EPUB_DIR_FOR_BACKFILL"/*_낭독판.epub(N); do
        RECOVER_CHECK=$(/opt/anaconda3/bin/python3 -c '
import os, re, sys
epub_path = sys.argv[1]
library_dir = sys.argv[2]
base = os.path.basename(epub_path)
base = re.sub(r"_낭독판\.epub$", "", base)
code = base.split(" — ", 1)[0].strip()
existing = os.listdir(library_dir) if os.path.isdir(library_dir) else []
found = any(t == code or t.startswith(code) for t in existing)
print("0" if found else "1")
' "$OLD_EPUB" "$LIBRARY_DIR")
        if [[ "$RECOVER_CHECK" != "1" ]]; then
            continue
        fi
        echo "🩹 library 원재료 없음 — EPUB에서 대사 복구 시도: ${OLD_EPUB:t}"
        if ! /opt/anaconda3/bin/python3 "${SCRIPT_DIR}/recover_study_cards_from_epub.py" "$OLD_EPUB"; then
            echo "⚠️  EPUB에서 대사 복구 실패 — 이 회차는 건너뜀"
        fi
    done
fi

if [[ -d "$LIBRARY_DIR" ]]; then
    for BOOK_CANDIDATE in "$LIBRARY_DIR"/*(N/); do
        TRANSCRIPT_FILES=("${BOOK_CANDIDATE}"/transcript_part*.jsonl(N))
        if [[ ${#TRANSCRIPT_FILES[@]} -eq 0 ]]; then
            continue
        fi
        CARDS_FILE="${BOOK_CANDIDATE}/scene_study_cards.json"
        NEEDS_RETRY=0
        if [[ ! -s "$CARDS_FILE" ]]; then
            NEEDS_RETRY=1
        elif ! /opt/anaconda3/bin/python3 -c '
import json, sys
try:
    data = json.load(open(sys.argv[1], encoding="utf-8"))
    sys.exit(0 if isinstance(data, dict) and data else 1)
except Exception:
    sys.exit(1)
' "$CARDS_FILE"; then
            NEEDS_RETRY=1
        fi
        if (( NEEDS_RETRY == 0 )); then
            continue
        fi
        echo "🩹 학습카드 없음 — 재시도: ${BOOK_CANDIDATE:t}"
        if ! /opt/anaconda3/bin/python3 "${SCRIPT_DIR}/generate_summary.py" "$BOOK_CANDIDATE"; then
            echo "⚠️  학습카드 복구 실패(쿼터 소진 등) — 다음 실행에서 다시 시도"
            continue
        fi
        RETRY_FINAL_EPUB="${BOOK_CANDIDATE}/${BOOK_CANDIDATE:t}.epub"
        if ! /opt/anaconda3/bin/python3 "${SCRIPT_DIR}/finalize_japanese_book.py" "$BOOK_CANDIDATE" \
            || [[ ! -f "$RETRY_FINAL_EPUB" ]]; then
            echo "⚠️  학습카드는 복구됐지만 EPUB 재빌드 실패 — 요약 자료는 보존됨"
            continue
        fi
        RETRY_DISPLAY_TITLE=$(
            /opt/anaconda3/bin/python3 "${SCRIPT_DIR}/book_title.py" \
                "$BOOK_CANDIDATE" --base-name "${BOOK_CANDIDATE:t}" --filename
        )
        [[ -z "$RETRY_DISPLAY_TITLE" ]] && RETRY_DISPLAY_TITLE="${BOOK_CANDIDATE:t}"
        RETRY_READALOUD_NAME="${RETRY_DISPLAY_TITLE}_낭독판.epub"
        RETRY_READALOUD_TMP="${MYTMP}/${RETRY_READALOUD_NAME}"
        if /opt/anaconda3/bin/python3 "${SCRIPT_DIR}/build_readaloud_epub.py" \
            "$BOOK_CANDIDATE" --output "$RETRY_READALOUD_TMP"; then
            mkdir -p "$COMPLETED_EPUB_DIR_FOR_BACKFILL"
            # 학습카드 없이 이미 배포됐던 옛 파일(같은 제목 접두사)을 지우고
            # 학습카드 포함 버전으로 교체한다.
            rm -f "${COMPLETED_EPUB_DIR_FOR_BACKFILL}/${BOOK_CANDIDATE:t}"*"_낭독판.epub"
            if cp "$RETRY_READALOUD_TMP" "${COMPLETED_EPUB_DIR_FOR_BACKFILL}/${RETRY_READALOUD_NAME}"; then
                echo "✅ 학습카드 포함 낭독판으로 교체 완료: ${RETRY_READALOUD_NAME}"
            else
                echo "⚠️  복구된 낭독판을 av완성작으로 복사하지 못함"
            fi
            rm -f "$RETRY_READALOUD_TMP"
        else
            echo "⚠️  학습카드는 복구됐지만 낭독판 EPUB 재빌드 실패"
        fi
    done
fi

echo "\n\033[1;35m==================================================\033[0m"
echo "\033[1;35m📝 자막·번역·Notion·EPUB 순차 처리 시작\033[0m"
echo "\033[1;35m==================================================\033[0m"

while true; do
    # 어떤 하위 명령이 현재 디렉터리를 바꾸더라도 다음 작품이 직전 작품 폴더
    # 안에 중첩되지 않도록 매 반복마다 사용자가 선택한 루트로 강제 복귀한다.
    cd "$WORKING_DIR" || exit 1
    CURRENT_FILES=(*.(mp4|webm|mkv|mov)(N))
    CURRENT_FILES=(${CURRENT_FILES:#*_운동용*})
    CURRENT_FILES=(${CURRENT_FILES:#*_고음영상*})

    FILENAME=""
    for CANDIDATE in "${CURRENT_FILES[@]}"; do
        ALREADY_ATTEMPTED=0
        for TRIED in "${ATTEMPTED_FILES[@]}"; do
            if [[ "$TRIED" == "$CANDIDATE" ]]; then
                ALREADY_ATTEMPTED=1
                break
            fi
        done
        if (( ! ALREADY_ATTEMPTED )); then
            FILENAME="$CANDIDATE"
            break
        fi
    done

    if [[ -z "$FILENAME" ]]; then
        break
    fi

    ATTEMPTED_FILES+=("$FILENAME")
    FILENAME_NO_EXT="${FILENAME%.*}"

    echo "\n\033[1;33m========================================\033[0m"
    echo "\033[1;33m🎬 영상 처리 시작: $FILENAME (시도 ${#ATTEMPTED_FILES[@]}번째)\033[0m"
    echo "\033[1;33m========================================\033[0m"

    TOTAL_SECS_RAW=$(ffprobe -v error -show_entries format=duration \
        -of default=noprint_wrappers=1:nokey=1 "$FILENAME" 2>/dev/null)
    TOTAL_SECS=${TOTAL_SECS_RAW%.*}
    [[ -z "$TOTAL_SECS" || "$TOTAL_SECS" -eq 0 ]] && TOTAL_SECS=1800

    TOTAL_MINS=$(( TOTAL_SECS / 60 ))

    if (( TOTAL_SECS >= 2700 )); then
        TOTAL_PARTS=2
        echo "📊 총 ${TOTAL_MINS}분 → 45분 이상: 2편 분할"
    else
        TOTAL_PARTS=1
        echo "📊 총 ${TOTAL_MINS}분 → 45분 미만: 단편 처리"
    fi

    CHUNK_DURATION=$(( TOTAL_SECS / TOTAL_PARTS ))
    PART_SRT_FILES=()
    PART_OFFSETS=()

    for (( PART=1; PART<=TOTAL_PARTS; PART++ )); do
        START_SEC=$(( (PART - 1) * CHUNK_DURATION ))
        START_MINS=$(( START_SEC / 60 ))
        (( PART == TOTAL_PARTS )) && CURRENT_CHUNK=$(( TOTAL_SECS - START_SEC )) || CURRENT_CHUNK=$CHUNK_DURATION

        echo "\n--------------------------------------------------"
        echo "📺 [$FILENAME_NO_EXT] $PART편 / ${TOTAL_PARTS}편 (구간: ${START_MINS}분~)"
        echo "--------------------------------------------------"

        TEMP_AUDIO="temp_${FILENAME_NO_EXT}_part${PART}.wav"
        PART_SRT="temp_${FILENAME_NO_EXT}_part${PART}.wav.srt"

        if [[ -f "$TEMP_AUDIO" ]]; then
            echo "♻️  오디오 캐시 재사용"
        else
            echo "🎵 오디오 추출 중..."
            _T0=$(date +%s)
            ffmpeg -ss "$START_SEC" -t "$CURRENT_CHUNK" -i "$FILENAME" \
                -ar 16000 -ac 1 -c:a pcm_s16le \
                -af "highpass=f=200,lowpass=f=3500,dynaudnorm=f=150:g=15" \
                "$TEMP_AUDIO" -y -loglevel error
            [[ $? -ne 0 ]] && echo "❌ 오디오 추출 실패" && continue
            echo "⏱ 오디오 추출 소요: $(( $(date +%s) - _T0 ))초"
        fi

        if [[ -f "$PART_SRT" ]]; then
            echo "♻️  자막 캐시 재사용"
        else
            echo "📝 Whisper 자막 분석 중..."
            _T0=$(date +%s)
            # ★ 2026-07-28: 속도 우선으로 튜닝(정확도와 속도 트레이드오프, 사용자 확인 후 결정).
            #   - beam-size 5→1(greedy): 빔서치는 매 토큰마다 후보 5개를 유지하며 디코딩해
            #     계산량이 greedy 대비 대략 5배 가깝게 든다. 자막처럼 짧은 발화 단위에서는
            #     정확도 손실이 크지 않다고 보고 최대 속도 쪽을 선택함.
            #   - p 4→1, t(기본4)→8: M2는 퍼포먼스 4 + 효율 4 = 8코어인데, 기존엔
            #     프로세스 4개 × 스레드 4개 = 16스레드가 8코어를 나눠 쓰고, Metal GPU도
            #     하나뿐이라 4개 프로세스가 같은 GPU를 두고 경쟁했다. 프로세스 1개가
            #     GPU와 8코어를 전부 쓰는 쪽이 더 빠를 것으로 예상 — 아래 ⏱ 로그로
            #     실측해서 맞지 않으면 이 값을 다시 조정할 것.
            #   - VAD_ARGS(--vad --vad-model, 위에서 준비): 무음/비음성 구간은 디코더를
            #     안 돌려서 크게 빨라진다. 종료 시각이 가끔 깨지는 버그가 있지만 이
            #     파이프라인은 그 값을 안 쓰므로 무시하고 켜둔다 — 자세한 경위는 위
            #     VAD_MODEL_PATH 자리의 주석 참조.
            $WHISPER_EXE -m "$MODEL_PATH" -f "./$TEMP_AUDIO" -osrt -l ja -p 1 -t 8 \
                "${VAD_ARGS[@]}" \
                --beam-size 1 --no-speech-thold 0.3 \
                --prompt "$WHISPER_PROMPT" > /dev/null 2>&1
            [[ ! -f "$PART_SRT" ]] && echo "❌ 자막 생성 실패" && continue
            echo "⏱ Whisper 자막 생성 소요: $(( $(date +%s) - _T0 ))초 (${CURRENT_CHUNK}초 분량 오디오)"
        fi

        PART_SRT_FILES+=("$PART_SRT")
        PART_OFFSETS+=("$START_SEC")

        PY_WORKER="${MYTMP}/worker_${FILENAME_NO_EXT}_${PART}.py"

        export PART_NUM="$PART"
        export TOTAL_PARTS_NUM="$TOTAL_PARTS"
        export START_OFFSET="$START_SEC"
        export CURRENT_SRT="$PART_SRT"
        export ORIGINAL_VIDEO="$FILENAME"
        export FILENAME_NO_EXT="$FILENAME_NO_EXT"
        export WORKING_DIR="$WORKING_DIR"
        export SCRIPT_DIR="$SCRIPT_DIR"
        export MYTMP="$MYTMP"

        cat << 'PYEOF' > "$PY_WORKER"
import os, sys, re, json, requests, time, subprocess, warnings, shutil, html
from datetime import datetime
from PIL import Image, ImageChops, ImageStat

warnings.filterwarnings("ignore", category=DeprecationWarning)
from pykakasi import kakasi
kks = kakasi()

# ── 단계별 소요시간 누적(어디서 시간이 제일 드는지 실행이 끝나면 바로 보여줌) ──
TIMING = {"translate": 0.0, "note": 0.0, "image": 0.0}

def clean_text(text):
    text = re.sub(r'\[.*?\]|\(.*?\)|\*.*?\*', '', text)
    if not re.search(r'[぀-ゟ゠-ヿ一-鿿]', text):
        return ""
    text = text.strip()
    if not text:
        return ""
    parts = re.split(r'[,、]', text)
    parts = [p.strip() for p in parts if p.strip()]
    if len(parts) >= 4:
        if len(set(parts)) / len(parts) < 0.3:
            return ""
    deduped = re.sub(r'(.{2,15})\1{2,}', r'\1', text)
    if deduped != text:
        text = deduped.strip()
        if not re.search(r'[぀-ゟ゠-ヿ一-鿿]', text):
            return ""
    if len(text) > 20:
        unique_chars = len(set(text.replace(' ', '').replace('、', '').replace('。', '')))
        if unique_chars / len(text) < 0.08:
            return ""
    return text

def generate_furigana(text):
    out = ""
    for item in kks.convert(text):
        orig, hira = item['orig'], item['hira']
        if orig != hira and re.search(r'[一-鿿々]', orig):
            out += f"{orig}({hira})"
        else:
            out += orig
    return out

TRANSLATION_MEMORY = {}
try:
    memory_path = os.path.join(os.environ.get("SCRIPT_DIR", ""), "translation_memory.json")
    with open(memory_path, encoding="utf-8") as memory_file:
        loaded_memory = json.load(memory_file)
        if isinstance(loaded_memory, dict):
            TRANSLATION_MEMORY = loaded_memory
except (OSError, ValueError):
    pass

# ★ 2026-09-03: "구글번역안되는게 너무 많다 최근에... 이유가 뭘까?" 질문 —
# 이 translate()는 Google의 비공식 무료 엔드포인트(translate.googleapis.com,
# googletrans류 도구가 쓰는 것과 동일)를 쓴다. 공식 유료 API가 아니라서
# 호출량이 늘면 Google이 IP 기준으로 자주 429(Too Many Requests)를 건다 —
# 코드 버그가 아니라 무료 엔드포인트의 태생적 한계. 실패한 문장은 아래
# TRANSLATION_MEMORY에 저장되지 않고 "[번역 실패]"로 남는데, 파이프라인
# 뒷단(refine_translations.py)이 "[번역 실패]"만은 검수 상한(--max-review)과
# 무관하게 전부 Codex/Claude로 문맥 기반 재번역하고, 그래도 남으면 최종 EPUB
# 생성 자체를 막는다 — 그래서 "dictionary화가 안 되고 그냥 넘어가는" 일은
# 없다(설계상 사전 없이 흘려보내는 걸 시스템이 스스로 막음). 다만 유사
# 문장을 사전 기준으로 "응용 해석"하는 퍼지 매칭은 일부러 안 넣었다 —
# "一人でしないの?"/"一人でするの?"처럼 부정 하나 차이로 뜻이 뒤집히는
# 문장이 흔해서, 유사도 기준 재사용은 눈치 못 채게 오역을 만들 위험이 있고
# refine_translations.py의 문맥 기반 AI 재번역이 이미 더 정확하다.
#
# 대신 진짜 비효율은 따로 있었다: Google이 지금 이 세션을 막고 있는 동안에도
# 문장마다 6회 지수 백오프를 그대로 반복해 문장 하나당 최대 수십 초씩
# 허비했다(사용자가 붙여준 로그처럼 연속으로 6/6 실패가 이어지는 구간).
# 이런 문장은 결국 "[번역 실패]"로 끝나 refine_translations.py로 넘어갈
# 뿐이므로, 연속 실패가 쌓이면(Google이 지금 막고 있다는 신호) 이후
# 문장들은 재시도 횟수를 크게 줄여 시간을 아낀다 — 최종 결과물 품질은
# 그대로(같은 refine_translations.py 경로), 쓸데없이 오래 기다리는 것만 줄인다.
_CONSECUTIVE_TRANSLATE_FAILURES = 0
TRANSLATE_CIRCUIT_BREAKER_THRESHOLD = 5
TRANSLATE_CIRCUIT_BREAKER_RETRIES = 2
_translate_circuit_breaker_announced = False


def translate(text, retries=6):
    global _CONSECUTIVE_TRANSLATE_FAILURES, _translate_circuit_breaker_announced
    _t0 = time.time()
    try:
        memory_key = text.strip()
        remembered = TRANSLATION_MEMORY.get(memory_key, "")
        if remembered and remembered != "[번역 실패]":
            return remembered
        effective_retries = retries
        if _CONSECUTIVE_TRANSLATE_FAILURES >= TRANSLATE_CIRCUIT_BREAKER_THRESHOLD:
            effective_retries = TRANSLATE_CIRCUIT_BREAKER_RETRIES
            if not _translate_circuit_breaker_announced:
                _translate_circuit_breaker_announced = True
                print(
                    f"⏭️ Google 번역이 연속 {_CONSECUTIVE_TRANSLATE_FAILURES}문장 실패 — "
                    f"지금 세션이 막힌 것으로 보고 이후 재시도를 {TRANSLATE_CIRCUIT_BREAKER_RETRIES}회로 "
                    "줄입니다(실패분은 뒤에서 Codex/Claude가 문맥 기반으로 다시 채웁니다).",
                    file=sys.stderr,
                )
        for attempt in range(effective_retries):
            try:
                url = (
                    "https://translate.googleapis.com/translate_a/single"
                    f"?client=gtx&sl=ja&tl=ko&dt=t&q={requests.utils.quote(text)}"
                )
                r = requests.get(url, timeout=12)
                if r.status_code == 200:
                    translated = "".join(s[0] for s in r.json()[0] if s[0]).strip()
                    if translated:
                        _CONSECUTIVE_TRANSLATE_FAILURES = 0
                        _translate_circuit_breaker_announced = False
                        return translated
                print(
                    f"⚠️ Google 번역 HTTP {r.status_code} "
                    f"(시도 {attempt + 1}/{effective_retries}, 원문 {memory_key[:30]!r})",
                    file=sys.stderr,
                )
            except Exception as exc:
                print(
                    f"⚠️ Google 번역 예외 {type(exc).__name__} "
                    f"(시도 {attempt + 1}/{effective_retries}, 원문 {memory_key[:30]!r})",
                    file=sys.stderr,
                )
            if attempt < effective_retries - 1:
                # 연속 요청 제한을 피하기 위한 지수 백오프. 작품 전체가 같은
                # 간격으로 재시도하지 않도록 현재 시각 기반의 작은 지연도 더한다.
                jitter = time.time() % 0.7
                time.sleep(min(20.0, 1.5 * (2 ** attempt)) + jitter)
        _CONSECUTIVE_TRANSLATE_FAILURES += 1
        return "[번역 실패]"
    finally:
        TIMING["translate"] += time.time() - _t0

def time_to_seconds(t):
    try:
        h, m, s = t.replace(',', '.').split(':')
        return float(h) * 3600 + float(m) * 60 + float(s)
    except Exception:
        return 0.0

def capture_representative_image(video_path, timestamp, out_path):
    """장면 중앙 시점의 대표 이미지 한 장만 캡처하고 EPUB 호환 JFIF로 정규화한다."""
    _t0 = time.time()
    try:
        if not os.path.exists(out_path):
            subprocess.run([
                "ffmpeg", "-y", "-ss", str(timestamp), "-i", video_path,
                "-vframes", "1", "-vf", "scale=960:-2", "-q:v", "4", out_path
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if not os.path.exists(out_path):
            return False
        subprocess.run(["sips", "-s", "format", "jpeg", out_path, "--out", out_path],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return os.path.getsize(out_path) > 0
    finally:
        TIMING["image"] += time.time() - _t0

def image_difference(path_a, path_b):
    """두 프레임의 밝기·구도 차이를 0~255 점수로 계산한다."""
    try:
        with Image.open(path_a) as a, Image.open(path_b) as b:
            a = a.convert("L").resize((96, 54))
            b = b.convert("L").resize((96, 54))
            return ImageStat.Stat(ImageChops.difference(a, b)).rms[0]
    except Exception:
        return 0.0

def prepare_scene_images(video_path, scene_lines, part_num, scene_num,
                         image_dir, scratch_dir):
    """앞쪽 대표 화면과, 충분히 다른 후반 화면을 최대 한 장 더 고른다.

    일정 간격으로 무조건 두 장을 넣지 않고 후반 후보 3장을 비교한다. 차이가
    작으면 보조 이미지를 생략하므로 같은 구도의 사진이 연달아 들어가지 않는다.
    """
    primary = os.path.join(
        image_dir, f"part{part_num}_scene{scene_num:03d}.jpg"
    )
    secondary = os.path.join(
        image_dir, f"part{part_num}_scene{scene_num:03d}_alt.jpg"
    )
    if not scene_lines:
        return primary, secondary if os.path.isfile(secondary) else None

    primary_idx = min(len(scene_lines) - 1, max(0, len(scene_lines) // 4))
    capture_representative_image(
        video_path, offset_sec + scene_lines[primary_idx]["start"] + 0.1, primary
    )
    if os.path.isfile(secondary):
        return primary, secondary

    candidate_indices = sorted(set([
        len(scene_lines) // 2,
        (len(scene_lines) * 3) // 4,
        max(0, len(scene_lines) - 2),
    ]))
    best_score, best_path = 0.0, None
    temp_paths = []
    os.makedirs(scratch_dir, exist_ok=True)
    for candidate_idx in candidate_indices:
        if candidate_idx <= primary_idx or candidate_idx >= len(scene_lines):
            continue
        temp_path = os.path.join(
            scratch_dir,
            f"part{part_num}_scene{scene_num:03d}_candidate{candidate_idx:03d}.jpg",
        )
        temp_paths.append(temp_path)
        capture_representative_image(
            video_path,
            offset_sec + scene_lines[candidate_idx]["start"] + 0.1,
            temp_path,
        )
        score = image_difference(primary, temp_path)
        if score > best_score:
            best_score, best_path = score, temp_path

    # 0~255 RMS 중 24 이상일 때만 상황 변화로 인정한다. 실제 신규 작업을
    # 보며 필요하면 JP_SECOND_IMAGE_THRESHOLD 환경변수로 조절할 수 있다.
    threshold = float(os.environ.get("JP_SECOND_IMAGE_THRESHOLD", "24"))
    if best_path and best_score >= threshold:
        shutil.copy2(best_path, secondary)
        print(f"   🖼️ 장면 {scene_num}: 다른 상황 이미지 추가 (차이 {best_score:.1f})")
    else:
        print(f"   🖼️ 장면 {scene_num}: 화면 변화가 작아 보조 이미지 생략 (차이 {best_score:.1f})")
    for temp_path in temp_paths:
        try:
            os.remove(temp_path)
        except OSError:
            pass
    return primary, secondary if os.path.isfile(secondary) else None

def create_epub_css(work_dir):
    """대표 이미지 한 장 주위로 대사가 흐르는 소설형 EPUB CSS.
    ★ 2026-07-31: 라이트/다크 모드에 따라 다른 배색을 쓰도록 재설계했다(사용자
    요청 — 라이트모드는 흰 배경에 검은/회색 글씨, 다크모드는 검은 배경에
    금색/회색 글씨). 기본(라이트) 스타일을 밖에 두고 `@media (prefers-color-
    scheme: dark)`로 다크모드 전용 값을 덮어쓴다. `:root { color-scheme: light
    dark; }`와 각 요소의 `ibooks-dark-theme-use-custom-text-color` 클래스는
    Apple Books 공식 가이드(Presentation and Styling)에 나온 요구사항 —
    이게 없으면 Apple Books가 다크 테마에서 커스텀 글자색을 전부 무시하고
    강제로 흰색 한 가지로 덮어써버린다(실제로 이 문제 때문에 일본어/한국어
    색 구분이 안 보인다는 사용자 리포트로 발견함)."""
    css_path = os.path.join(work_dir, "epub_style.css")
    css = """\
:root {
    color-scheme: light dark;
}
body {
    font-family: "Hiragino Kaku Gothic Pro", "ヒラギノ角ゴ Pro", sans-serif;
    background-color: #ffffff;
    color: #1a1a1a;
    line-height: 1.6;
    padding: 1em;
}
h1 {
    color: #9a6a00;
    border-bottom: 2px solid #9a6a00;
    padding-bottom: 0.3em;
}
h2.scene {
    color: #9a6a00;
    font-size: 1.15em;
    margin-top: 1.8em;
    margin-bottom: 0.6em;
    padding: 0.3em 0.6em;
    background-color: #f2f2f2;
    border-left: 4px solid #9a6a00;
}
div.set {
    margin-bottom: 0.9em;
    padding-bottom: 0.7em;
    border-bottom: 1px solid #e0e0e0;
}
img.scene-thumb {
    width: 60%;
    max-width: 32em;
    border-radius: 4px;
    margin: 0.25em 1.1em 0.7em 0;
    float: left;
    opacity: 0.92;
}
.scene-end {
    clear: both;
}
p.scene-desc {
    font-style: italic;
    font-size: 0.92em;
    color: #555555;
    margin-top: 0.3em;
    margin-bottom: 1em;
}
p.ja {
    font-size: 1.2em;
    font-weight: bold;
    color: #000000;
    letter-spacing: 0.03em;
    margin-bottom: 0.1em;
    margin-top: 0.5em;
}
p.ko {
    font-size: 0.82em;
    color: #808080;
    margin-top: 0;
    margin-bottom: 0.15em;
    padding-left: 0.5em;
    border-left: 2px solid #cccccc;
}
div.overview {
    background-color: #f5f5f5;
    border: 1px solid #dddddd;
    border-radius: 8px;
    padding: 1.2em 1.4em;
    margin-bottom: 1.5em;
}
div.overview h2 {
    color: #9a6a00;
    margin-top: 0;
}
div.overview table {
    width: 100%;
    border-collapse: collapse;
}
div.overview td {
    padding: 0.3em 0.5em;
    border-bottom: 1px solid #e0e0e0;
}
div.overview td:first-child {
    color: #666666;
    width: 40%;
}
nav#toc a { color: #9a6a00; text-decoration: none; }

@media (prefers-color-scheme: dark) {
    body {
        background-color: #111111;
        color: #dddddd;
    }
    h1 {
        color: #f5c842;
        border-bottom-color: #f5c842;
    }
    h2.scene {
        color: #f5c842;
        background-color: #1c1c1c;
        border-left-color: #f5c842;
    }
    div.set {
        border-bottom-color: #2a2a2a;
    }
    p.scene-desc {
        color: #aaaaaa;
    }
    p.ja {
        color: #f5c842;
    }
    p.ko {
        color: #777777;
        border-left-color: #333333;
    }
    div.overview {
        background-color: #1a1a1a;
        border-color: #333333;
    }
    div.overview h2 {
        color: #f5c842;
    }
    div.overview td {
        border-bottom-color: #2a2a2a;
    }
    div.overview td:first-child {
        color: #999999;
    }
    nav#toc a { color: #f5c842; }
}
"""
    with open(css_path, "w", encoding="utf-8") as f:
        f.write(css)
    return css_path

# 장면 하나는 대사 24줄이다. 대표 이미지 1장과, 상황이 충분히 달라질 때만
# 후반 보조 이미지 1장을 추가한다.
SCENE_SIZE = 8

def save_to_md(work_dir, note_title, representative_img_path, secondary_img_path,
               ja_list, ko_list, part_num="1", chunk_idx=0):
    base_name  = os.environ.get("FILENAME_NO_EXT", "result")
    result_dir = os.path.join(work_dir, f"{base_name}_work")
    img_dir    = os.path.join(result_dir, "images")
    os.makedirs(img_dir,   exist_ok=True)

    img_filename = None
    if representative_img_path and os.path.exists(representative_img_path):
        img_filename = os.path.basename(representative_img_path)
        shutil.copy2(representative_img_path, os.path.join(img_dir, img_filename))
    secondary_filename = None
    if secondary_img_path and os.path.exists(secondary_img_path):
        secondary_filename = os.path.basename(secondary_img_path)
        shutil.copy2(secondary_img_path, os.path.join(img_dir, secondary_filename))

    md_path = os.path.join(work_dir, f"{note_title}.md")
    if not os.path.exists(md_path):
        total_lines = len(parsed_lines)
        total_sets  = TOTAL_SETS
        scene_count = (total_sets + SCENE_SIZE - 1) // SCENE_SIZE
        overview = f"""# {note_title} {{.ibooks-dark-theme-use-custom-text-color}}

<div class="overview">
<h2 class="ibooks-dark-theme-use-custom-text-color">📋 개요</h2>
<table>
<tr><td>파트</td><td>{part_num} / {total_parts}편</td></tr>
<tr><td>대사 문장 수</td><td>{total_lines}줄</td></tr>
<tr><td>장면 수</td><td>{scene_count}개 (장면당 대사 약 {SCENE_SIZE * 3}줄)</td></tr>
<tr><td>표기 방식</td><td>원문 위(금색, 한자엔 후리가나 병기) / 번역 아래(회색)</td></tr>
<tr><td>이미지</td><td>장면마다 대표 이미지 1장 + 상황 변화가 클 때 보조 이미지 1장</td></tr>
</table>
</div>

"""
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(overview)

    scene_num = (chunk_idx - 1) // SCENE_SIZE + 1
    with open(md_path, "a", encoding="utf-8") as f:
        if (chunk_idx - 1) % SCENE_SIZE == 0:
            # ★ 마크다운 네이티브 헤더 문법({.scene}은 pandoc 헤더 속성 확장)을
            # 써야 --toc가 이걸 목차 항목으로 잡는다. <h2> raw HTML로 쓰면
            # pandoc이 그냥 불투명한 블록으로 취급해서 목차에 안 잡힌다(확인됨).
            # ibooks-dark-theme-use-custom-text-color: Apple Books가 다크
            # 테마에서 커스텀 글자색을 무시하지 않게 하는 공식 클래스(아래
            # p.ja/p.ko에도 동일하게 적용).
            f.write(f'## 🎬 장면 {scene_num} {{.scene .ibooks-dark-theme-use-custom-text-color}}\n\n')
            if img_filename:
                f.write(f'<img class="scene-thumb" src="{base_name}_work/images/{img_filename}" alt="장면 {scene_num}" />\n\n')
        elif (chunk_idx - 1) % SCENE_SIZE == SCENE_SIZE // 2 and secondary_filename:
            f.write(f'<div class="scene-end"></div>\n\n<img class="scene-thumb" src="{base_name}_work/images/{secondary_filename}" alt="장면 {scene_num} 상황 변화" />\n\n')
        f.write('<div class="set">\n\n')
        for ja, ko in zip(ja_list, ko_list):
            furi = generate_furigana(ja)
            f.write(f'<p class="ja ibooks-dark-theme-use-custom-text-color">{html.escape(furi)}</p>\n')
            f.write(f'<p class="ko ibooks-dark-theme-use-custom-text-color">{html.escape(ko)}</p>\n\n')
        f.write("</div>\n\n")
        if chunk_idx % SCENE_SIZE == 0:
            f.write('<div class="scene-end"></div>\n\n')


# ── Apple Notes ───────────────────────────────────────────────────
MYTMP        = os.environ.get("MYTMP", os.path.expanduser("~"))
SCPT_PATH    = os.path.join(MYTMP, "ls_applescript_tmp.scpt")
TITLE_PATH   = os.path.join(MYTMP, "ls_note_title.txt")
CONTENT_PATH = os.path.join(MYTMP, "ls_note_content.txt")

def run_applescript(script_text):
    with open(SCPT_PATH, "w", encoding="utf-8") as f:
        f.write(script_text)
    result = subprocess.run(["osascript", SCPT_PATH], capture_output=True, text=True)
    try: os.remove(SCPT_PATH)
    except: pass
    return result

def create_apple_note(note_title):
    with open(TITLE_PATH, "w", encoding="utf-8") as f:
        f.write(note_title)
    script = f'''
set titleFile to "{TITLE_PATH}"
set noteTitle to do shell script "cat " & quoted form of titleFile
tell application "Notes"
    activate
    delay 0.5
    tell account "iCloud"
        if not (exists folder "LanguageStudy") then
            make new folder with properties {{name:"LanguageStudy"}}
            delay 0.5
        end if
        set matchingNotes to (every note of folder "LanguageStudy" whose name is noteTitle)
        repeat with n in matchingNotes
            delete n
        end repeat
        make new note at folder "LanguageStudy" with properties {{name:noteTitle, body:""}}
    end tell
end tell
'''
    _t0 = time.time()
    result = run_applescript(script)
    TIMING["note"] += time.time() - _t0
    if result.returncode == 0:
        print(f"📱 메모 앱 노트 생성: {note_title}")
    else:
        print(f"⚠️  메모 앱 노트 생성 실패: {result.stderr.strip()}")

def append_to_apple_note(note_title, ja_lines):
    with open(TITLE_PATH, "w", encoding="utf-8") as f:
        f.write(note_title)
    with open(CONTENT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(ja_lines) + "\n\n")
    script = f'''
set titleFile   to "{TITLE_PATH}"
set contentFile to "{CONTENT_PATH}"
set noteTitle   to do shell script "cat " & quoted form of titleFile
set newContent  to do shell script "cat " & quoted form of contentFile
tell application "Notes"
    tell account "iCloud"
        set targetNote to first note of folder "LanguageStudy" whose name is noteTitle
        set body of targetNote to (body of targetNote) & newContent
    end tell
end tell
'''
    _t0 = time.time()
    result = run_applescript(script)
    TIMING["note"] += time.time() - _t0
    if result.returncode != 0:
        print(f"⚠️  메모 앱 append 실패: {result.stderr.strip()}")

# ── 환경변수 ──────────────────────────────────────────────────────
part_num    = os.environ.get("PART_NUM", "1")
total_parts = os.environ.get("TOTAL_PARTS_NUM", "1")
offset_sec  = float(os.environ.get("START_OFFSET", 0))
srt_path    = os.environ["CURRENT_SRT"]
video_path  = os.environ["ORIGINAL_VIDEO"]
base_name   = os.environ["FILENAME_NO_EXT"]
work_dir    = os.environ.get("WORKING_DIR", ".")
script_dir  = os.environ.get("SCRIPT_DIR", work_dir)

img_folder = os.path.join(work_dir, f"{base_name}_scenes_part{part_num}")
os.makedirs(img_folder, exist_ok=True)
safe_base_name = re.sub(r'[^0-9A-Za-z가-힣._-]+', '_', base_name).strip('_') or "untitled"
book_dir = os.path.join(script_dir, "library", safe_base_name)
book_images_dir = os.path.join(book_dir, "images")
os.makedirs(book_images_dir, exist_ok=True)

# ── SRT 파싱 ─────────────────────────────────────────────────────
with open(srt_path, 'r', encoding='utf-8', errors='ignore') as f:
    raw_blocks = f.read().strip().split('\n\n')

parsed_lines, seen = [], set()
for block in raw_blocks:
    lines = block.split('\n')
    if len(lines) >= 3 and ' --> ' in lines[1]:
        times = lines[1].split(' --> ')
        text  = clean_text("".join(lines[2:]))
        if not text or text in seen:
            continue
        seen.add(text)
        parsed_lines.append({
            'start': time_to_seconds(times[0].strip()),
            'end':   time_to_seconds(times[1].strip()),
            'text':  text
        })

if not parsed_lines:
    print("⚠️  유효한 자막 없음")
    sys.exit(0)

# 낭독판 EPUB은 페이지당 4문장이므로 각 고정 페이지에 대응하는 화면을
# 미리 캡처한다. 파일명에 장면 안 페이지 번호를 넣어 재빌드할 때도 재사용한다.
READALOUD_LINES_PER_PAGE = 4
for scene_start in range(0, len(parsed_lines), SCENE_SIZE * 3):
    scene_num = scene_start // (SCENE_SIZE * 3) + 1
    scene_lines = parsed_lines[scene_start:scene_start + SCENE_SIZE * 3]
    page_groups = [scene_lines[:2]] + [
        scene_lines[i:i + READALOUD_LINES_PER_PAGE]
        for i in range(2, len(scene_lines), READALOUD_LINES_PER_PAGE)
    ]
    for page_num, page_lines in enumerate(page_groups, 1):
        representative = page_lines[len(page_lines) // 2]
        page_image = os.path.join(
            book_images_dir,
            f"part{part_num}_scene{scene_num:03d}_page{page_num:02d}.jpg",
        )
        capture_representative_image(
            video_path, offset_sec + representative["start"] + 0.1, page_image
        )
print(
    f"🖼️ 낭독판 EPUB 페이지 이미지 준비 완료 "
    f"(장면 첫 페이지 2문장+학습 카드, 이후 페이지당 {READALOUD_LINES_PER_PAGE}문장)",
    flush=True,
)

# ── 로컬 책 자료 생성 (Notion 연동은 사용하지 않음) ───────────────
now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
if total_parts == "1":
    note_title   = base_name
else:
    note_title   = f"{base_name} 제{part_num}편"
TOTAL_SETS = (len(parsed_lines) + 2) // 3
print(f"🚀 [{base_name}] 로컬 EPUB 자료 준비 │ 총 {len(parsed_lines)}줄 / {TOTAL_SETS}세트")
print(f"📚 Git 책 자료 폴더: {book_dir}\n")

create_epub_css(work_dir)
create_epub_css(book_dir)
create_apple_note(note_title)

transcript_jsonl = os.path.join(book_dir, f"transcript_part{part_num}.jsonl")
transcript_md = os.path.join(book_dir, f"transcript_part{part_num}.md")
with open(transcript_jsonl, "w", encoding="utf-8") as f:
    pass
with open(transcript_md, "w", encoding="utf-8") as f:
    f.write(f"# {base_name} 제{part_num}편 전체 대사 {{.ibooks-dark-theme-use-custom-text-color}}\n\n")

summary_path = os.path.join(book_dir, "SUMMARY.md")
if not os.path.exists(summary_path):
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write(
            f"# {base_name} 줄거리·목차 {{.ibooks-dark-theme-use-custom-text-color}}\n\n"
            "> Codex 요약 대기 중 — transcript_part*.jsonl과 대표 이미지를 읽고 작성한다.\n\n"
            "## 전체 줄거리\n\n"
            "요약 대기 중\n\n"
            "## 장면별 목차\n\n"
            "요약 대기 중\n"
        )

# ── 3문장씩 처리 ─────────────────────────────────────────────────
_PIPELINE_START = time.time()
scene_primary_path = None
scene_secondary_path = None
for idx in range(0, len(parsed_lines), 3):
    chunk     = parsed_lines[idx:idx + 3]
    chunk_idx = idx // 3 + 1
    n         = len(chunk)

    ja_list = [c['text'] for c in chunk]
    ko_list = [translate(t) for t in ja_list]

    scene_num = (chunk_idx - 1) // SCENE_SIZE + 1
    representative_path = None
    if (chunk_idx - 1) % SCENE_SIZE == 0:
        scene_lines = parsed_lines[idx:idx + SCENE_SIZE * 3]
        scene_primary_path, scene_secondary_path = prepare_scene_images(
            video_path, scene_lines, part_num, scene_num,
            book_images_dir, img_folder,
        )
        representative_path = scene_primary_path

    with open(transcript_jsonl, "a", encoding="utf-8") as jf, \
         open(transcript_md, "a", encoding="utf-8") as mf:
        if (chunk_idx - 1) % SCENE_SIZE == 0:
            # {.scene}이 있어야 h2.scene CSS(금색/배경)가 적용되고 --toc 목차에도
            # 잡힌다. ibooks-dark-theme-use-custom-text-color는 Apple Books
            # 다크 테마에서 이 색이 흰색으로 강제 대체되지 않게 하는 공식 클래스.
            mf.write(f"## 장면 {scene_num} {{.scene .ibooks-dark-theme-use-custom-text-color}}\n\n")
            mf.write(f'<img class="scene-thumb" src="images/part{part_num}_scene{scene_num:03d}.jpg" alt="장면 {scene_num}" />\n\n')
        elif ((chunk_idx - 1) % SCENE_SIZE == SCENE_SIZE // 2
              and scene_secondary_path and os.path.isfile(scene_secondary_path)):
            mf.write(
                '<div class="scene-end"></div>\n\n'
                f'<img class="scene-thumb" src="images/{os.path.basename(scene_secondary_path)}" '
                f'alt="장면 {scene_num} 상황 변화" />\n\n'
            )
        for c, ja, ko in zip(chunk, ja_list, ko_list):
            furi = generate_furigana(ja)
            record = {
                "part": int(part_num),
                "scene": scene_num,
                "start": offset_sec + c["start"],
                "end": offset_sec + c["end"],
                "ja": ja,
                "furigana": furi,
                "ko": ko,
            }
            jf.write(json.dumps(record, ensure_ascii=False) + "\n")
            # ★ 2026-07-28: 예전엔 마크다운 볼드(`- **{furi}**`)로만 썼는데, 이러면
            # CSS 클래스가 없어서 epub_style.css의 p.ja(금색)/p.ko(회색) 색 구분이
            # 전혀 적용 안 되고 본문 기본색으로만 보였다 — save_to_md()가 쓰는
            # _work 폴더 md와 똑같이 클래스 있는 HTML로 맞춘다.
            mf.write(f'<p class="ja ibooks-dark-theme-use-custom-text-color">{html.escape(furi)}</p>\n')
            mf.write(f'<p class="ko ibooks-dark-theme-use-custom-text-color">{html.escape(ko)}</p>\n\n')
        mf.write("\n")

    append_to_apple_note(note_title, ja_list)

    save_to_md(work_dir, note_title, representative_path, scene_secondary_path,
               ja_list, ko_list, part_num=part_num, chunk_idx=chunk_idx)

    processed_lines = min(idx + n, len(parsed_lines))
    if chunk_idx % SCENE_SIZE == 0 or processed_lines == len(parsed_lines):
        total_scenes = (len(parsed_lines) + SCENE_SIZE * 3 - 1) // (SCENE_SIZE * 3)
        print(
            f"   📚 진행: 장면 {scene_num}/{total_scenes} · "
            f"대사 {processed_lines}/{len(parsed_lines)}줄 "
            f"({processed_lines / len(parsed_lines):.0%})",
            flush=True,
        )

scene_count = (TOTAL_SETS + SCENE_SIZE - 1) // SCENE_SIZE
print(f"\n✅ [{base_name}] {part_num}/{total_parts}편 완료 │ "
      f"{scene_count}장면 / 대표 이미지 {scene_count}장")

_pipeline_elapsed = time.time() - _PIPELINE_START
print(
    f"⏱ [{base_name}] {part_num}편 3문장-루프 소요 세부 — "
    f"번역 {TIMING['translate']:.1f}초 · "
    f"메모앱 {TIMING['note']:.1f}초 · 이미지캡처 {TIMING['image']:.1f}초 "
    f"(루프 전체 {_pipeline_elapsed:.1f}초)"
)
PYEOF
        _T0=$(date +%s)
        if ! /opt/anaconda3/bin/python3 "$PY_WORKER"; then
            echo "❌ [$FILENAME_NO_EXT] 제 $PART편 처리 실패 — 이 영상의 후속 EPUB 작업을 중단합니다."
            rm -f "$PY_WORKER"
            PART_PIPELINE_FAILED=1
            break
        fi
        echo "⏱ 번역/메모앱 처리(전체) 소요: $(( $(date +%s) - _T0 ))초"
        rm -f "$PY_WORKER"
        echo "✅ [$FILENAME_NO_EXT] 제 $PART편 완료."
    done

    if [[ "${PART_PIPELINE_FAILED:-0}" -eq 1 ]]; then
        unset PART_PIPELINE_FAILED
        echo "⚠️  [$FILENAME_NO_EXT] 실패한 원본은 현재 위치에 유지합니다. 다음 영상으로 넘어갑니다."
        continue
    fi

    SAFE_BASE_NAME=$(printf '%s' "$FILENAME_NO_EXT" | sed -E 's/[^0-9A-Za-z가-힣._-]+/_/g; s/^_+//; s/_+$//')
    BOOK_DIR="${SCRIPT_DIR}/library/${SAFE_BASE_NAME}"

    # ── 통합 자막 생성 ─────────────────────────────────────────────
    MERGED_SRT="${FILENAME_NO_EXT}.srt"
    echo "\n📄 통합 자막 생성 중: $MERGED_SRT"

    MERGE_PY="${MYTMP}/merge_srt_${FILENAME_NO_EXT}.py"

    PARTS_JSON="["
    for (( i=0; i<${#PART_SRT_FILES[@]}; i++ )); do
        PARTS_JSON+="{\"srt\":\"${PART_SRT_FILES[$i+1]}\",\"offset\":${PART_OFFSETS[$i+1]}}"
        (( i < ${#PART_SRT_FILES[@]} - 1 )) && PARTS_JSON+=","
    done
    PARTS_JSON+="]"

    /opt/anaconda3/bin/python3 - << PYMERGE
import json
from datetime import timedelta

parts      = json.loads('${PARTS_JSON}')
output_srt = "${MERGED_SRT}"

def sec2srt(s):
    td = timedelta(seconds=s)
    t  = int(td.total_seconds())
    ms = int((td.total_seconds() - t) * 1000)
    return f"{t//3600:02d}:{(t%3600)//60:02d}:{t%60:02d},{ms:03d}"

def srt2sec(t):
    try:
        h, m, s = t.replace(',', '.').split(':')
        return float(h)*3600 + float(m)*60 + float(s)
    except:
        return 0.0

entries = []
for part in parts:
    offset = float(part['offset'])
    try:
        with open(part['srt'], 'r', encoding='utf-8', errors='ignore') as f:
            for block in f.read().strip().split('\n\n'):
                lines = block.split('\n')
                if len(lines) >= 3 and ' --> ' in lines[1]:
                    t0, t1 = lines[1].split(' --> ')
                    text   = '\n'.join(lines[2:]).strip()
                    if text:
                        entries.append((srt2sec(t0.strip())+offset,
                                        srt2sec(t1.strip())+offset, text))
    except Exception as e:
        print(f"⚠️  {part['srt']} 읽기 실패: {e}")

entries.sort(key=lambda x: x[0])
with open(output_srt, 'w', encoding='utf-8') as f:
    for i, (s, e, t) in enumerate(entries, 1):
        f.write(f"{i}\n{sec2srt(s)} --> {sec2srt(e)}\n{t}\n\n")

print(f"✅ 통합 자막: {output_srt} ({len(entries)}개)")
PYMERGE

    # ── EPUB 생성 ─────────────────────────────────────────────────
    echo "\n📚 EPUB 생성 중..."
    command -v pandoc &>/dev/null || brew install pandoc

    CSS_FILE="${WORKING_DIR}/epub_style.css"

    # ★ 2026-07-24: 예전엔 본문에 쓰던 3장짜리 가로 합성 썸네일(1440x270,
    #   책 표지로 쓰기엔 너무 납작한 배너 모양)을 그대로 표지로 재사용했다.
    #   대신 원본 영상에서 세로 표지 비율로 직접 한 장을 새로 뽑아서 제목을
    #   입힌다. 또한 ffmpeg가 만든 jpg는 표준 JFIF 헤더가 없어서 pandoc이
    #   가로/세로를 못 읽는 문제(EPUB 안에서 표지가 0x0으로 깨짐)가 있었는데,
    #   `sips`로 다시 저장해서 표준 JFIF로 정규화하면 해결된다(확인 완료).
    COVER_FILE="${WORKING_DIR}/${FILENAME_NO_EXT}_work/cover.jpg"
    SNAP_AT=$(( TOTAL_SECS / 25 ))
    (( SNAP_AT < 5 ))  && SNAP_AT=5
    (( SNAP_AT > 90 )) && SNAP_AT=90

    # ★ 2026-07-24: 이 ffmpeg 호출을 터미널에서 직접 실행하면 항상 성공하는데,
    # 실제 파이프라인(백그라운드로 오래 도는 실행) 안에서는 가끔 조용히
    # 실패하는 경우가 있었다(원인 미확정 — 리소스 경합으로 추정). 원인을
    # 못 찾았으니 최소한 재발 시 바로 알 수 있게 stderr를 로그 파일로 남긴다.
    COVER_LOG="${MYTMP}/cover_${FILENAME_NO_EXT}.log"
    /opt/anaconda3/bin/ffmpeg -y -ss "$SNAP_AT" -i "$FILENAME" -vframes 1 \
        -vf "crop=ih*2/3:ih:(iw-ih*2/3)/2:0,scale=960:1440,\
drawbox=x=0:y=1150:w=960:h=290:color=black@0.55:t=fill,\
drawtext=fontfile='/System/Library/Fonts/Supplemental/Arial Bold.ttf':text='${FILENAME_NO_EXT}':fontcolor=white:fontsize=90:x=(w-text_w)/2:y=1230,\
drawtext=fontfile='/System/Library/Fonts/Supplemental/Arial.ttf':text='Japanese Subtitle Study':fontcolor=#cccccc:fontsize=34:x=(w-text_w)/2:y=1340" \
        -q:v 3 "$COVER_FILE" > "$COVER_LOG" 2>&1

    if [[ ! -s "$COVER_FILE" ]]; then
        echo "⚠️ 영상 표지 캡처 실패 — 추출된 장면 이미지로 대체 표지 생성"
        /opt/anaconda3/bin/python3 "${SCRIPT_DIR}/create_fallback_cover.py" \
            "$BOOK_DIR" "$COVER_FILE" "$FILENAME_NO_EXT" \
            || echo "⚠️ 장면 이미지 대체 표지도 생성하지 못했습니다"
    fi

    if [[ -f "$COVER_FILE" ]]; then
        sips -s format jpeg "$COVER_FILE" --out "$COVER_FILE" &>/dev/null
        echo "🎨 표지 준비 완료 (${SNAP_AT}초 지점, 세로 960x1440)"
        # ★ 2026-07-31: library/<작품명>/에도 복사해둔다 — finalize_japanese_book.py가
        # 나중에(요약 자동화 단계에서) 만드는 최종 EPUB은 여기서 만든 "빠른" EPUB과
        # 별도 pandoc 호출이라, 표지를 안 챙기면 최종 EPUB에서 표지가 사라진다
        # (실제로 이 버그가 발견되어 추가함).
        mkdir -p "$BOOK_DIR"
        cp "$COVER_FILE" "${BOOK_DIR}/cover.jpg"
    else
        COVER_FILE=""
        echo "⚠️  표지 캡처 실패 — 로그: $COVER_LOG"
        tail -20 "$COVER_LOG"
    fi

    if (( TOTAL_PARTS == 1 )); then
        MD_FILES=("${FILENAME_NO_EXT}.md")
    else
        MD_FILES=("${FILENAME_NO_EXT} 제1편.md" "${FILENAME_NO_EXT} 제2편.md")
    fi

    EXISTING_MDS=()
    for mdf in "${MD_FILES[@]}"; do
        [[ -f "$mdf" ]] && EXISTING_MDS+=("$mdf")
    done

    OUTPUT_EPUB="${FILENAME_NO_EXT}.epub"
    EPUB_LOG="${MYTMP}/pandoc_${FILENAME_NO_EXT}.log"

    if (( ${#EXISTING_MDS[@]} > 0 )); then
        # ★ 2026-07-23: --epub-version=3 는 pandoc 3.x에서 삭제된 옵션이라
        #   항상 즉시 실패했었다(Unknown option). -o *.epub만으로 이미 EPUB3로
        #   나오므로 그냥 뺀다. 또한 에러를 2>/dev/null로 숨기지 않고 로그 파일에
        #   남겨서, 실패해도 원인을 바로 알 수 있게 한다.
        PANDOC_ARGS=(
            "${EXISTING_MDS[@]}"
            "--resource-path=.:./${FILENAME_NO_EXT}_work:./${FILENAME_NO_EXT}_work/audio:./${FILENAME_NO_EXT}_work/images"
            "-o" "$OUTPUT_EPUB"
            "--metadata" "title=${FILENAME_NO_EXT}"
            "--metadata" "author=LanguageStudy"
            "--toc"
            "--toc-depth=2"
            "--standalone"
        )
        [[ -f "$CSS_FILE" ]]   && PANDOC_ARGS+=("--css=${CSS_FILE}")
        [[ -f "$COVER_FILE" ]] && PANDOC_ARGS+=("--epub-cover-image=${COVER_FILE}")

        _T0=$(date +%s)
        pandoc "${PANDOC_ARGS[@]}" > "$EPUB_LOG" 2>&1
        echo "⏱ pandoc EPUB 빌드 소요: $(( $(date +%s) - _T0 ))초"

        if [[ -f "$OUTPUT_EPUB" ]]; then
            SIZE=$(du -sh "$OUTPUT_EPUB" | cut -f1)
            echo "✅ EPUB 생성 완료: $OUTPUT_EPUB (${SIZE})"

            OBSIDIAN_PATH="/Users/forrestdpark/Library/Mobile Documents/iCloud~md~obsidian/Documents/Study"
        else
            echo "⚠️  EPUB 생성 실패 — 아래 pandoc 오류 로그 확인:"
            cat "$EPUB_LOG"
        fi
    else
        echo "⚠️  MD 파일 없음, EPUB 건너뜀"
    fi

    # ── 자동 요약·학습 카드 + 최종 낭독판 EPUB ──────────────────────
    # Google 번역 전체를 AI로 다시 번역하지 않는다. 코드가 오역 가능성이 높다고
    # 판정한 일부 문장만 앞뒤 일본어 문맥과 함께 작품당 한 번 Codex로 검수하고,
    # 확정 결과는 translation_memory.json에 저장해 다음 작품에서 즉시 재사용한다.
    echo "\n🔎 Google 번역 이상 문장 선택 검수 중..."
    if ! /opt/anaconda3/bin/python3 "${SCRIPT_DIR}/refine_translations.py" "$BOOK_DIR"; then
        echo "❌ 번역 실패 문장이 남아 이 작품의 최종 EPUB 생성을 중단합니다."
        echo "   작업 자료는 $BOOK_DIR 에 보존되므로 검수 재실행 후 이어서 만들 수 있습니다."
        continue
    fi

    # ★ 2026-07-28: 원래 "Codex가 transcript_part*.jsonl과 대표 이미지를 읽고
    #   SUMMARY.md를 작성한다"는 수동 단계였는데, 여기까지 자동으로 끝난 뒤
    #   요약만 사람이 따로 세션을 열어야 하는 게 병목이었다. Claude Code CLI의
    #   헤드리스 --print 모드(generate_summary.py)로 대사 텍스트(ja/ko)만 보고
    #   "전체 줄거리"+"장면별 목차"+"장면별 학습 카드"를 쓰게 해서 자동화함.
    #   요약이 준비되면 finalize_japanese_book.py가 SUMMARY.md +
    #   전체 대사를 합쳐 목차 포함 최종 EPUB을 새로 만든다 — 이 최종본이 이미
    #   만든 "빠른" EPUB(줄거리 없음)보다 항상 나으므로 $OUTPUT_EPUB을 덮어써서
    #   교체하고, 옵시디언에도 다시 복사한다.
    echo "\n🧠 Codex로 줄거리·장면별 학습 카드 자동 생성 중..."
    READALOUD_SUCCESS=0
    READALOUD_EPUB=""
    SUMMARY_OK=0
    COMPLETED_EPUB_DIR="/Users/forrestdpark/Desktop/BlogImage/av완성작"
    mkdir -p "$COMPLETED_EPUB_DIR"
    _T0=$(date +%s)
    if /opt/anaconda3/bin/python3 "${SCRIPT_DIR}/generate_summary.py" "$BOOK_DIR"; then
        SUMMARY_OK=1
        echo "⏱ 요약 생성 소요: $(( $(date +%s) - _T0 ))초"

        FINAL_LIBRARY_EPUB="${BOOK_DIR}/${SAFE_BASE_NAME}.epub"
        if /opt/anaconda3/bin/python3 "${SCRIPT_DIR}/finalize_japanese_book.py" "$BOOK_DIR" \
            && [[ -f "$FINAL_LIBRARY_EPUB" ]]; then
            cp "$FINAL_LIBRARY_EPUB" "$OUTPUT_EPUB"
            echo "✅ 줄거리·목차 포함된 최종 EPUB으로 교체: $OUTPUT_EPUB"
        else
            echo "⚠️  최종 EPUB 빌드 실패 — 줄거리 없는 기존 EPUB 유지"
        fi
    else
        echo "⚠️  요약 생성 실패(AI 토큰/쿼터 소진 등) — SUMMARY.md는 '요약 대기 중' 상태로 남음"
        echo "    낭독판은 학습카드·줄거리 없이 TTS 낭독만으로 계속 만듭니다."
        echo "    (나중에 요약만 재생성: python3 generate_summary.py \"$BOOK_DIR\")"
    fi

    # ★ 2026-08-07: 낭독판(TTS) EPUB은 whisper 대사 텍스트만 있으면 만들 수 있고
    # AI(Codex/Claude)가 필요 없다 — 학습카드·줄거리만 AI가 필요하다. 예전엔
    # generate_summary.py 실패 시 이 블록 전체를 건너뛰어서 AI 쿼터가 없으면
    # 낭독판 자체가 하나도 안 만들어졌다. 이제 요약 성공 여부와 무관하게 항상
    # 시도한다 — 성공하면 학습카드 포함, 실패하면 학습카드 없이 TTS 낭독만.
    # Read Aloud EPUB을 유일한 최종 배포본으로 만든다. 일반 EPUB은 낭독판
    # 생성 실패 시 비상 결과물 및 내부 재빌드용이다. 일본어 42px, 페이지당
    # 4문장, 두 페이지 펼침(auto), 문장별 SMIL 강조, 페이지 내 '자동 읽기'
    # 버튼의 자동 넘김이 표준 양식이다.
    EPUB_DISPLAY_TITLE=$(
        /opt/anaconda3/bin/python3 "${SCRIPT_DIR}/book_title.py" \
            "$BOOK_DIR" --base-name "$FILENAME_NO_EXT" --filename
    )
    [[ -z "$EPUB_DISPLAY_TITLE" ]] && EPUB_DISPLAY_TITLE="$FILENAME_NO_EXT"
    READALOUD_EPUB="${EPUB_DISPLAY_TITLE}_낭독판.epub"
    echo "\n📖 Apple Books 문장 동기화·자동 넘김 EPUB 생성 중..."
    _T0=$(date +%s)
    if /opt/anaconda3/bin/python3 "${SCRIPT_DIR}/build_readaloud_epub.py" \
        "$BOOK_DIR" --output "$READALOUD_EPUB"; then
        echo "⏱ 낭독판 EPUB 생성 소요: $(( $(date +%s) - _T0 ))초"
        FINAL_BOOKS_EPUB="${COMPLETED_EPUB_DIR}/${READALOUD_EPUB:t}"
        if cp "$READALOUD_EPUB" "$FINAL_BOOKS_EPUB"; then
            echo "📖 낭독판 EPUB 완성작 폴더 복사 완료"
            # 작업 폴더와 배포 위치에는 낭독판 EPUB 하나만 남긴다.
            # library 안의 일반 EPUB은 재빌드용 내부 자료로 보존한다.
            rm -f "$OUTPUT_EPUB"
            rm -f "${COMPLETED_EPUB_DIR}/${FILENAME_NO_EXT}.epub"
            [[ -d "$OBSIDIAN_PATH" ]] && rm -f \
                "${OBSIDIAN_PATH}/${FILENAME_NO_EXT}.epub" \
                "${OBSIDIAN_PATH}/${READALOUD_EPUB:t}"
            READALOUD_SUCCESS=1
            if (( SUMMARY_OK == 0 )); then
                echo "⚠️  주의: 이 낭독판에는 AI 요약·학습카드가 빠져 있습니다(쿼터 소진 등)."
                echo "    나중에 python3 generate_summary.py \"$BOOK_DIR\" 로 요약만 채운 뒤"
                echo "    이 스크립트를 재실행하면 학습카드가 포함된 낭독판으로 교체됩니다."
            fi
            if [[ "${JP_OPEN_BOOKS:-1}" != "0" ]]; then
                if open -a Books "$FINAL_BOOKS_EPUB"; then
                    echo "📖 Apple Books에서 최종 EPUB을 열었습니다."
                else
                    echo "⚠️  EPUB은 정상 생성됐지만 Apple Books 자동 열기에 실패했습니다."
                fi
            fi
        else
            echo "⚠️  낭독판 EPUB 완성작 폴더 복사 실패 — 자동 열기를 건너뜁니다."
        fi
    else
        echo "⚠️  낭독판 EPUB 생성 실패 — 일반 EPUB은 정상 보존하며, 나중에 재실행 가능"
    fi

    # 낭독판 EPUB이 실패했을 때만 일반 EPUB을 비상 결과물로 배포한다.
    if (( READALOUD_SUCCESS == 0 )) && [[ -f "$OUTPUT_EPUB" ]]; then
        cp "$OUTPUT_EPUB" "$COMPLETED_EPUB_DIR/" \
            && echo "📚 낭독판 실패로 일반 EPUB을 비상 보존"
    fi

    echo "\033[1;32m[$FILENAME_NO_EXT] 전체 완료!\033[0m"
    echo "  📄 자막: $MERGED_SRT"
    if (( READALOUD_SUCCESS == 1 )); then
        echo "  📖 최종 EPUB: $READALOUD_EPUB"
    else
        echo "  📚 비상 EPUB: $OUTPUT_EPUB"
    fi

    # ── 최종 폴더 정리 ────────────────────────────────────────────
    # 최상위(<파일명>/)에는 원본 영상 + EPUB + BGM 운동용 영상 3개만
    # 보이게 하고, 나머지 작업 파일(자막/후리가나 md/썸네일/캐시 등)은
    # <파일명>/기타/ 로 몰아서 정리한다.
    FINAL_DIR="${WORKING_DIR}/${FILENAME_NO_EXT}"
    mkdir -p "${FINAL_DIR}/기타"

    HIGHLIGHT_BGM=$(ls "${FILENAME_NO_EXT}_운동용_"*"_bgm.mp4"(N) 2>/dev/null | head -1)
    EXTRACTION_HISTORY="${FILENAME_NO_EXT}_운동용_추출기록.json"
    AVMUSIC_EXPORT_RECORDED=0
    AVMUSIC_EXPORTED_NAME=""
    if [[ -f "$EXTRACTION_HISTORY" ]]; then
        AVMUSIC_EXPORT_INFO=$(python3 -c '
import json, sys
try:
    data = json.load(open(sys.argv[1], encoding="utf-8"))
    item = data.get("avmusic_export") or {}
    size = int(item.get("size") or 0)
    name = str(item.get("file") or "")
    if size > 0 and name:
        print(f"{size}\t{name}")
except Exception:
    pass
' "$EXTRACTION_HISTORY")
        if [[ -n "$AVMUSIC_EXPORT_INFO" ]]; then
            AVMUSIC_EXPORT_RECORDED=1
            AVMUSIC_EXPORTED_NAME="${AVMUSIC_EXPORT_INFO#*$'\t'}"
        fi
    fi
    HIGHLIGHT_PLAIN_ALL=("${FILENAME_NO_EXT}_운동용_"*.mp4(N))
    HIGHLIGHT_PLAIN=""
    for hf in "${HIGHLIGHT_PLAIN_ALL[@]}"; do
        [[ "$hf" != *_bgm.mp4 ]] && HIGHLIGHT_PLAIN="$hf"
    done

    [[ -f "$FILENAME" ]] && mv "$FILENAME" "$FINAL_DIR/"
    [[ -f "$OUTPUT_EPUB" ]] && mv "$OUTPUT_EPUB" "$FINAL_DIR/"
    [[ -n "$READALOUD_EPUB" && -f "$READALOUD_EPUB" ]] \
        && mv "$READALOUD_EPUB" "$FINAL_DIR/"
    [[ -n "$HIGHLIGHT_BGM" ]] && mv "$HIGHLIGHT_BGM" "$FINAL_DIR/"

    [[ -n "$HIGHLIGHT_PLAIN" ]] && mv "$HIGHLIGHT_PLAIN" "$FINAL_DIR/기타/"
    [[ -f "$MERGED_SRT" ]] && mv "$MERGED_SRT" "$FINAL_DIR/기타/"
    for f in "${FILENAME_NO_EXT}"*.md(N); do mv "$f" "$FINAL_DIR/기타/"; done
    [[ -d "${FILENAME_NO_EXT}_work" ]] && mv "${FILENAME_NO_EXT}_work" "$FINAL_DIR/기타/"
    for d in "${FILENAME_NO_EXT}_scenes_part"*(N); do mv "$d" "$FINAL_DIR/기타/"; done
    for f in "temp_${FILENAME_NO_EXT}_part"*.wav(N) "temp_${FILENAME_NO_EXT}_part"*.wav.srt(N) \
             "temp_${FILENAME_NO_EXT}_pitch.wav"(N) \
             "${FILENAME_NO_EXT}_운동용_추출기록.json"(N); do
        mv "$f" "$FINAL_DIR/기타/"
    done

    # 최종 낭독판이 존재하고, BGM 영상이 avMusic에 현재 있거나 이번 실행에서
    # 크기 검증까지 마친 복사 기록이 있을 때 중간 작업물을 삭제한다. 사용자가
    # 복사 직후 avMusic 파일을 다른 곳으로 옮겨도 불필요한 대용량 캐시를 남기지 않는다.
    AV_MUSIC_DIR="/Users/forrestdpark/Desktop/BlogImage/avMusic"
    FINAL_EPUB_COPY="${COMPLETED_EPUB_DIR}/${READALOUD_EPUB:t}"
    AV_MUSIC_MATCHES=("${AV_MUSIC_DIR}/${FILENAME_NO_EXT}_운동용_"*"_bgm.mp4"(N))
    # subtitle_notion_epub_only.sh로 단독 실행했을 땐 운동용 영상 추출 자체가
    # 없으므로(WORKOUT_EXTRACTION_ENABLED=0) avMusic 확인을 요구하지 않는다 —
    # 안 그러면 이 경로로 처리한 원본은 영원히 정리 조건을 못 채워 폴더에 계속 쌓인다.
    WORKOUT_CONFIRMED=0
    if (( WORKOUT_EXTRACTION_ENABLED == 0 )); then
        WORKOUT_CONFIRMED=1
    elif (( ${#AV_MUSIC_MATCHES[@]} > 0 || AVMUSIC_EXPORT_RECORDED == 1 )); then
        WORKOUT_CONFIRMED=1
    fi
    if (( READALOUD_SUCCESS == 1 )) \
        && [[ -s "$FINAL_EPUB_COPY" ]] \
        && (( WORKOUT_CONFIRMED == 1 )); then
        echo "🧹 최종 파일 확인 — 원본은 보존하고 중간 작업물 삭제"
        echo "   📖 $FINAL_EPUB_COPY"
        if (( WORKOUT_EXTRACTION_ENABLED == 0 )); then
            echo "   🎵 이번 실행은 운동용 영상 추출 없음(자막·번역·EPUB 단독 실행)"
        elif (( ${#AV_MUSIC_MATCHES[@]} > 0 )); then
            echo "   🎵 ${AV_MUSIC_MATCHES[1]}"
        else
            echo "   🎵 avMusic 복사 완료 기록 확인(현재 파일은 이동됨): $AVMUSIC_EXPORTED_NAME"
        fi
        ORIGINAL_IN_FINAL="${FINAL_DIR}/${FILENAME:t}"
        ORIGINAL_PRESERVED=0
        if [[ -f "$ORIGINAL_IN_FINAL" ]]; then
            mv "$ORIGINAL_IN_FINAL" "./${FILENAME:t}"
            echo "   🎬 원본 영상 보존: ./${FILENAME:t}"
            ORIGINAL_PRESERVED=1
        elif [[ -f "./${FILENAME:t}" ]]; then
            echo "   🎬 원본 영상 확인: ./${FILENAME:t}"
            ORIGINAL_PRESERVED=1
        fi
        if (( ORIGINAL_PRESERVED == 1 )); then
            if [[ -n "$FINAL_DIR" && "$FINAL_DIR" != "." && -d "$FINAL_DIR" ]]; then
                rm -rf -- "$FINAL_DIR"
            fi
            # ★ 2026-09-04: "epub 에서 학습카드가 없는경우에는 학습카드를 다시
            # 만들도록 파이프라인 수정하면 좋겠어" 요청으로 실측 확인한 원인 —
            # generate_summary.py가 AI 쿼터 소진 등으로 실패해도(SUMMARY_OK=0)
            # 낭독판 EPUB 자체는 whisper 대사만으로 만들어져 av완성작에
            # 배포된다. 예전엔 이 정리 단계가 SUMMARY_OK를 확인하지 않고
            # library/<제목>/ 폴더(BOOK_DIR)를 통째로 지워서, 학습카드를 나중에
            # 다시 만들 원재료(transcript_part*.jsonl)까지 같이 사라졌다
            # (WAAA-681·IPZZ-923·EBWH-356 라이브러리 폴더가 흔적도 없이
            # 사라진 걸로 실측 확인). 이제 학습카드가 실제로 만들어졌을
            # 때(SUMMARY_OK==1)만 지운다 — 실패한 경우는 아래 "학습카드 누락
            # 회차 자동 복구" 단계가 다음 실행에서 재시도할 수 있게 보존한다.
            if (( SUMMARY_OK == 1 )) \
                && [[ -n "$BOOK_DIR" && "$BOOK_DIR" == "${SCRIPT_DIR}/library/"* \
                      && -d "$BOOK_DIR" ]]; then
                rm -rf -- "$BOOK_DIR"
            elif (( SUMMARY_OK == 0 )); then
                echo "🩹 학습카드 미생성 — library 원재료는 다음 실행 자동 복구를 위해 보존: $BOOK_DIR"
            fi
            echo "✅ 정리 완료 — 원본 영상 + av완성작 낭독판 + avMusic BGM 영상 보존"
        else
            echo "⚠️ 원본 영상 보존을 확인하지 못해 중간 작업물을 삭제하지 않음"
        fi
    else
        echo "⚠️ 최종 파일 확인 불완전 — 원본과 중간 작업물을 삭제하지 않음"
        echo "   낭독판: $FINAL_EPUB_COPY"
        echo "   avMusic BGM 후보: ${#AV_MUSIC_MATCHES[@]}개"
        echo "   avMusic 복사 완료 기록: $AVMUSIC_EXPORT_RECORDED"
    fi
    COMPLETED_COUNT=$(( COMPLETED_COUNT + 1 ))
    echo "✅ 현재 실행에서 완료한 원본: ${COMPLETED_COUNT}개"
done

echo "\n=================================================="
echo "🎉 모든 영상 처리 완료! (완료 ${COMPLETED_COUNT}개 / 시도 ${#ATTEMPTED_FILES[@]}개)"
echo "=================================================="
osascript -e "display notification \"완료 ${COMPLETED_COUNT}개 / 시도 ${#ATTEMPTED_FILES[@]}개\" with title \"LanguageStudy ✅\""
afplay /System/Library/Sounds/Glass.aiff
sleep 2
