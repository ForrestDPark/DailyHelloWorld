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

# 시작할 때 만든 상대경로 배열만 순회하면 첫 영상 정리 후 실행 상태에 따라
# 후속 파일이 누락돼도 복구할 수 없다. 영상 하나가 끝날 때마다 폴더를 다시
# 스캔해서 아직 시도하지 않은 원본을 하나씩 꺼내는 큐 방식으로 처리한다.
# 실패해 원본이 그대로 남은 파일은 ATTEMPTED_FILES로 기억해 무한 재시도하지 않는다.
ATTEMPTED_FILES=()
COMPLETED_COUNT=0

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

while true; do
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
            ffmpeg -ss "$START_SEC" -t "$CURRENT_CHUNK" -i "$FILENAME" \
                -ar 16000 -ac 1 -c:a pcm_s16le \
                -af "highpass=f=200,lowpass=f=3500,dynaudnorm=f=150:g=15" \
                "$TEMP_AUDIO" -y -loglevel error
            [[ $? -ne 0 ]] && echo "❌ 오디오 추출 실패" && continue
        fi

        if [[ -f "$PART_SRT" ]]; then
            echo "♻️  자막 캐시 재사용"
        else
            echo "📝 Whisper 자막 분석 중..."
            $WHISPER_EXE -m "$MODEL_PATH" -f "./$TEMP_AUDIO" -osrt -l ja -p 4 \
                --beam-size 5 --no-speech-thold 0.3 \
                --prompt "$WHISPER_PROMPT" > /dev/null 2>&1
            [[ ! -f "$PART_SRT" ]] && echo "❌ 자막 생성 실패" && continue
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
        export MYTMP="$MYTMP"

        cat << 'PYEOF' > "$PY_WORKER"
import os, sys, re, json, requests, time, subprocess, warnings, shutil
from datetime import datetime

warnings.filterwarnings("ignore", category=DeprecationWarning)
from pykakasi import kakasi
kks = kakasi()

# ── 시크릿은 코드에 하드코딩하지 않고 macOS 키체인에서 읽는다 ──────────
# 등록: security add-generic-password -a "$USER" -s "jp_subtitle_notion_token" -w "<토큰>" -U
def load_secret(service_name):
    try:
        result = subprocess.run(
            ["security", "find-generic-password", "-a", os.environ.get("USER", ""),
             "-s", service_name, "-w"],
            capture_output=True, text=True, check=True,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return None

NOTION_TOKEN      = load_secret("jp_subtitle_notion_token")
DATABASE_ID       = "35f32a1eae808058a38af59076445e42"

if not NOTION_TOKEN:
    print("❌ 노션 토큰을 키체인에서 찾을 수 없습니다. README의 키체인 등록 명령을 먼저 실행하세요.")
    sys.exit(1)

headers = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

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

def translate(text, retries=3):
    for attempt in range(retries):
        try:
            url = (
                "https://translate.googleapis.com/translate_a/single"
                f"?client=gtx&sl=ja&tl=ko&dt=t&q={requests.utils.quote(text)}"
            )
            r = requests.get(url, timeout=7)
            if r.status_code == 200:
                return "".join(s[0] for s in r.json()[0] if s[0])
        except Exception:
            pass
        if attempt < retries - 1:
            time.sleep(1.5 * (attempt + 1))
    return "[번역 실패]"

def time_to_seconds(t):
    try:
        h, m, s = t.replace(',', '.').split(':')
        return float(h) * 3600 + float(m) * 60 + float(s)
    except Exception:
        return 0.0

def capture_representative_image(video_path, timestamp, out_path):
    """장면 중앙 시점의 대표 이미지 한 장만 캡처하고 EPUB 호환 JFIF로 정규화한다."""
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

def notion_append(url, children, retries=3):
    for attempt in range(retries):
        try:
            r = requests.patch(url, headers=headers,
                               json={"children": children}, timeout=15)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(1.5 * (attempt + 1))
    return False

def build_monitor_blocks(img_url, ja_list, ko_list):
    blocks = []
    LABEL_COLORS = ["orange", "yellow", "green"]
    if img_url:
        blocks.append({
            "object": "block", "type": "image",
            "image": {"type": "external", "external": {"url": img_url}}
        })
    for i, (ja, ko) in enumerate(zip(ja_list, ko_list)):
        color = LABEL_COLORS[i] if i < len(LABEL_COLORS) else "default"
        furi  = generate_furigana(ja)
        blocks.append({
            "object": "block", "type": "quote",
            "quote": {
                "rich_text": [
                    {"type": "text",
                     "text": {"content": f"▶ {furi}"},
                     "annotations": {"bold": True, "color": color}},
                    {"type": "text",
                     "text": {"content": f"  →  {ko}"},
                     "annotations": {"bold": False, "color": "gray"}}
                ],
                "color": "default"
            }
        })
    blocks.append({"object": "block", "type": "paragraph",
                   "paragraph": {"rich_text": []}})
    return blocks

def create_epub_css(work_dir):
    """대표 이미지 한 장 주위로 대사가 흐르는 소설형 EPUB CSS."""
    css_path = os.path.join(work_dir, "epub_style.css")
    css = """\
body {
    font-family: "Hiragino Kaku Gothic Pro", "ヒラギノ角ゴ Pro", sans-serif;
    background-color: #111111;
    color: #dddddd;
    line-height: 1.6;
    padding: 1em;
}
h1 {
    color: #f5c842;
    border-bottom: 2px solid #f5c842;
    padding-bottom: 0.3em;
}
h2.scene {
    color: #f5c842;
    font-size: 1.15em;
    margin-top: 1.8em;
    margin-bottom: 0.6em;
    padding: 0.3em 0.6em;
    background-color: #1c1c1c;
    border-left: 4px solid #f5c842;
}
div.set {
    margin-bottom: 0.9em;
    padding-bottom: 0.7em;
    border-bottom: 1px solid #2a2a2a;
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
p.ja {
    font-size: 1.2em;
    font-weight: bold;
    color: #f5c842;
    letter-spacing: 0.03em;
    margin-bottom: 0.1em;
    margin-top: 0.5em;
}
p.ko {
    font-size: 0.82em;
    color: #777777;
    margin-top: 0;
    margin-bottom: 0.15em;
    padding-left: 0.5em;
    border-left: 2px solid #333333;
}
div.overview {
    background-color: #1a1a1a;
    border: 1px solid #333333;
    border-radius: 8px;
    padding: 1.2em 1.4em;
    margin-bottom: 1.5em;
}
div.overview h2 {
    color: #f5c842;
    margin-top: 0;
}
div.overview table {
    width: 100%;
    border-collapse: collapse;
}
div.overview td {
    padding: 0.3em 0.5em;
    border-bottom: 1px solid #2a2a2a;
}
div.overview td:first-child {
    color: #999999;
    width: 40%;
}
nav#toc a { color: #f5c842; text-decoration: none; }
"""
    with open(css_path, "w", encoding="utf-8") as f:
        f.write(css)
    return css_path

# 장면 하나는 대사 24줄이며 대표 이미지는 장면마다 단 한 장만 사용한다.
SCENE_SIZE = 8

def save_to_md(work_dir, note_title, representative_img_path, ja_list, ko_list,
               part_num="1", chunk_idx=0):
    base_name  = os.environ.get("FILENAME_NO_EXT", "result")
    result_dir = os.path.join(work_dir, f"{base_name}_work")
    img_dir    = os.path.join(result_dir, "images")
    os.makedirs(img_dir,   exist_ok=True)

    img_filename = None
    if representative_img_path and os.path.exists(representative_img_path):
        img_filename = os.path.basename(representative_img_path)
        shutil.copy2(representative_img_path, os.path.join(img_dir, img_filename))

    md_path = os.path.join(work_dir, f"{note_title}.md")
    if not os.path.exists(md_path):
        total_lines = len(parsed_lines)
        total_sets  = TOTAL_SETS
        scene_count = (total_sets + SCENE_SIZE - 1) // SCENE_SIZE
        overview = f"""# {note_title}

<div class="overview">
<h2>📋 개요</h2>
<table>
<tr><td>파트</td><td>{part_num} / {total_parts}편</td></tr>
<tr><td>대사 문장 수</td><td>{total_lines}줄</td></tr>
<tr><td>장면 수</td><td>{scene_count}개 (장면당 대사 약 {SCENE_SIZE * 3}줄)</td></tr>
<tr><td>표기 방식</td><td>원문 위(금색, 한자엔 후리가나 병기) / 번역 아래(회색)</td></tr>
<tr><td>이미지</td><td>장면마다 대표 이미지 1장, 대사가 이미지 주위로 흐르는 책형 배치</td></tr>
</table>
</div>

"""
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(overview)

    with open(md_path, "a", encoding="utf-8") as f:
        if (chunk_idx - 1) % SCENE_SIZE == 0:
            scene_num = (chunk_idx - 1) // SCENE_SIZE + 1
            # ★ 마크다운 네이티브 헤더 문법({.scene}은 pandoc 헤더 속성 확장)을
            # 써야 --toc가 이걸 목차 항목으로 잡는다. <h2> raw HTML로 쓰면
            # pandoc이 그냥 불투명한 블록으로 취급해서 목차에 안 잡힌다(확인됨).
            f.write(f'## 🎬 장면 {scene_num} {{.scene}}\n\n')
            if img_filename:
                f.write(f'<img class="scene-thumb" src="{base_name}_work/images/{img_filename}" alt="장면 {scene_num}" />\n\n')
        f.write('<div class="set">\n\n')
        for ja, ko in zip(ja_list, ko_list):
            furi = generate_furigana(ja)
            f.write(f'<p class="ja">{furi}</p>\n')
            f.write(f'<p class="ko">{ko}</p>\n\n')
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
    result = run_applescript(script)
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
    result = run_applescript(script)
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

# ── Notion 페이지 생성 ────────────────────────────────────────────
now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
if total_parts == "1":
    title        = f"📖 {base_name} ({now_str})"
    callout_text = f"🍿  {base_name}"
    note_title   = base_name
else:
    title        = f"📖 {base_name} [제 {part_num}편] ({now_str})"
    callout_text = f"🍿  {base_name}  제 {part_num}편"
    note_title   = f"{base_name} 제{part_num}편"

page_res = requests.post("https://api.notion.com/v1/pages", headers=headers, json={
    "parent": {"database_id": DATABASE_ID},
    "icon":   {"type": "emoji", "emoji": "🎬"},
    "properties": {
        "내용": {"title": [{"text": {"content": title}}]},
        "상태": {"select": {"name": "추출 중"}},
        "요약 상태": {"select": {"name": "대기"}},
        "Git 경로": {"rich_text": [{"text": {
            "content": f"일본어자막추출/library/{safe_base_name}"
        }}]},
    },
    "children": [{
        "object": "block", "type": "callout",
        "callout": {
            "rich_text": [{"type": "text", "text": {"content": callout_text}}],
            "icon":  {"type": "emoji", "emoji": "📺"},
            "color": "orange_background"
        }
    }]
})

if page_res.status_code != 200:
    print(f"❌ Notion 페이지 생성 실패: {page_res.status_code}")
    sys.exit(1)

page_id   = page_res.json()["id"]
child_url = f"https://api.notion.com/v1/blocks/{page_id}/children"
TOTAL_SETS = (len(parsed_lines) + 2) // 3
print(f"🚀 [{base_name}] Notion 연동 완료 │ 총 {len(parsed_lines)}줄 / {TOTAL_SETS}세트")
print(f"📚 Git 책 자료 폴더: {book_dir}\n")

create_epub_css(work_dir)
create_epub_css(book_dir)
create_apple_note(note_title)

with open(os.path.join(book_dir, f"notion_part{part_num}.json"), "w", encoding="utf-8") as f:
    json.dump({
        "database_id": DATABASE_ID,
        "page_id": page_id,
        "page_url": f"https://www.notion.so/{page_id.replace('-', '')}",
        "title": title,
        "git_relative_path": f"일본어자막추출/library/{safe_base_name}",
        "image_status": "Notion 파일 직접 업로드 대기",
        "summary_status": "Codex 요약 대기",
    }, f, ensure_ascii=False, indent=2)

transcript_jsonl = os.path.join(book_dir, f"transcript_part{part_num}.jsonl")
transcript_md = os.path.join(book_dir, f"transcript_part{part_num}.md")
with open(transcript_jsonl, "w", encoding="utf-8") as f:
    pass
with open(transcript_md, "w", encoding="utf-8") as f:
    f.write(f"# {base_name} 제{part_num}편 전체 대사\n\n")

summary_path = os.path.join(book_dir, "SUMMARY.md")
if not os.path.exists(summary_path):
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write(
            f"# {base_name} 줄거리·목차\n\n"
            "> Codex 요약 대기 중 — transcript_part*.jsonl과 대표 이미지를 읽고 작성한다.\n\n"
            "## 전체 줄거리\n\n"
            "요약 대기 중\n\n"
            "## 장면별 목차\n\n"
            "요약 대기 중\n"
        )

# ── 3문장씩 처리 ─────────────────────────────────────────────────
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
        representative = scene_lines[len(scene_lines) // 2]
        representative_path = os.path.join(
            book_images_dir, f"part{part_num}_scene{scene_num:03d}.jpg"
        )
        capture_representative_image(
            video_path,
            offset_sec + representative["start"] + 0.1,
            representative_path,
        )

    with open(transcript_jsonl, "a", encoding="utf-8") as jf, \
         open(transcript_md, "a", encoding="utf-8") as mf:
        if (chunk_idx - 1) % SCENE_SIZE == 0:
            mf.write(f"## 장면 {scene_num}\n\n")
            mf.write(f'<img class="scene-thumb" src="images/part{part_num}_scene{scene_num:03d}.jpg" alt="장면 {scene_num}" />\n\n')
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
            mf.write(f"- **{furi}**  \n  {ko}\n")
        mf.write("\n")

    # 대표 이미지는 전체 추출 뒤 Notion File Upload API로 직접 업로드한다.
    # 추출 단계에서는 텍스트만 기록하고, Codex 후처리 단계가 줄거리·목차를
    # 완성한다.
    uploaded_url  = None
    notion_blocks = build_monitor_blocks(uploaded_url, ja_list, ko_list)
    for i in range(0, len(notion_blocks), 20):
        notion_append(child_url, notion_blocks[i:i+20])
        time.sleep(0.3)

    append_to_apple_note(note_title, ja_list)

    save_to_md(work_dir, note_title, representative_path, ja_list, ko_list,
               part_num=part_num, chunk_idx=chunk_idx)

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
requests.patch(
    f"https://api.notion.com/v1/pages/{page_id}",
    headers=headers,
    json={"properties": {
        "상태": {"select": {"name": "요약 대기"}},
        "요약 상태": {"select": {"name": "대기"}},
        "대표 이미지 수": {"number": scene_count},
    }},
    timeout=15,
)
print(f"\n✅ [{base_name}] {part_num}/{total_parts}편 완료 │ "
      f"{scene_count}장면 / 대표 이미지 {scene_count}장")
PYEOF
        /opt/anaconda3/bin/python3 "$PY_WORKER"
        rm -f "$PY_WORKER"
        echo "✅ [$FILENAME_NO_EXT] 제 $PART편 완료."
    done

    # ── 대표 이미지 Notion 저장소 직접 업로드 ──────────────────────
    SAFE_BASE_NAME=$(printf '%s' "$FILENAME_NO_EXT" | sed -E 's/[^0-9A-Za-z가-힣._-]+/_/g; s/^_+//; s/_+$//')
    BOOK_DIR="${SCRIPT_DIR}/library/${SAFE_BASE_NAME}"
    echo "\n🖼️ 대표 이미지 Notion 직접 업로드 중..."
    /opt/anaconda3/bin/python3 "${SCRIPT_DIR}/sync_book_to_notion.py" \
        --images-only "$BOOK_DIR" || echo "⚠️ Notion 이미지 업로드 실패 — 나중에 재실행 가능"

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
    ffmpeg -y -ss "$SNAP_AT" -i "$FILENAME" -vframes 1 \
        -vf "crop=ih*2/3:ih:(iw-ih*2/3)/2:0,scale=960:1440,\
drawbox=x=0:y=1150:w=960:h=290:color=black@0.55:t=fill,\
drawtext=fontfile='/System/Library/Fonts/Supplemental/Arial Bold.ttf':text='${FILENAME_NO_EXT}':fontcolor=white:fontsize=90:x=(w-text_w)/2:y=1230,\
drawtext=fontfile='/System/Library/Fonts/Supplemental/Arial.ttf':text='Japanese Subtitle Study':fontcolor=#cccccc:fontsize=34:x=(w-text_w)/2:y=1340" \
        -q:v 3 "$COVER_FILE" > "$COVER_LOG" 2>&1

    if [[ -f "$COVER_FILE" ]]; then
        sips -s format jpeg "$COVER_FILE" --out "$COVER_FILE" &>/dev/null
        echo "🎨 표지 준비 완료 (${SNAP_AT}초 지점, 세로 960x1440)"
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

        pandoc "${PANDOC_ARGS[@]}" > "$EPUB_LOG" 2>&1

        if [[ -f "$OUTPUT_EPUB" ]]; then
            SIZE=$(du -sh "$OUTPUT_EPUB" | cut -f1)
            echo "✅ EPUB 생성 완료: $OUTPUT_EPUB (${SIZE})"

            OBSIDIAN_PATH="/Users/forrestdpark/Library/Mobile Documents/iCloud~md~obsidian/Documents/Study"
            [[ -d "$OBSIDIAN_PATH" ]] && cp "$OUTPUT_EPUB" "$OBSIDIAN_PATH/" \
                && echo "📂 옵시디언 복사 완료"
        else
            echo "⚠️  EPUB 생성 실패 — 아래 pandoc 오류 로그 확인:"
            cat "$EPUB_LOG"
        fi
    else
        echo "⚠️  MD 파일 없음, EPUB 건너뜀"
    fi

    echo "\033[1;32m[$FILENAME_NO_EXT] 전체 완료!\033[0m"
    echo "  📄 자막: $MERGED_SRT"
    echo "  📚 EPUB: $OUTPUT_EPUB"

    # ── 최종 폴더 정리 ────────────────────────────────────────────
    # 최상위(<파일명>/)에는 원본 영상 + EPUB + BGM 운동용 영상 3개만
    # 보이게 하고, 나머지 작업 파일(자막/후리가나 md/썸네일/캐시 등)은
    # <파일명>/기타/ 로 몰아서 정리한다.
    FINAL_DIR="$FILENAME_NO_EXT"
    mkdir -p "${FINAL_DIR}/기타"

    HIGHLIGHT_BGM=$(ls "${FILENAME_NO_EXT}_운동용_"*"_bgm.mp4"(N) 2>/dev/null | head -1)
    HIGHLIGHT_PLAIN_ALL=("${FILENAME_NO_EXT}_운동용_"*.mp4(N))
    HIGHLIGHT_PLAIN=""
    for hf in "${HIGHLIGHT_PLAIN_ALL[@]}"; do
        [[ "$hf" != *_bgm.mp4 ]] && HIGHLIGHT_PLAIN="$hf"
    done

    [[ -f "$FILENAME" ]] && mv "$FILENAME" "$FINAL_DIR/"
    [[ -f "$OUTPUT_EPUB" ]] && mv "$OUTPUT_EPUB" "$FINAL_DIR/"
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

    echo "📦 최종 폴더 정리 완료:"
    echo "   $FINAL_DIR/  (원본 영상 + EPUB + BGM 운동용 영상)"
    echo "   $FINAL_DIR/기타/  (자막/md/썸네일/캐시 등 나머지)"
    COMPLETED_COUNT=$(( COMPLETED_COUNT + 1 ))
    echo "✅ 현재 실행에서 완료한 원본: ${COMPLETED_COUNT}개"
done

echo "\n=================================================="
echo "🎉 모든 영상 처리 완료! (완료 ${COMPLETED_COUNT}개 / 시도 ${#ATTEMPTED_FILES[@]}개)"
echo "=================================================="
osascript -e "display notification \"완료 ${COMPLETED_COUNT}개 / 시도 ${#ATTEMPTED_FILES[@]}개\" with title \"LanguageStudy ✅\""
afplay /System/Library/Sounds/Glass.aiff
sleep 2
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
