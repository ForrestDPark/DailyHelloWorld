#!/bin/zsh
# 일본어 영상 → 자막(Whisper) + 번역(구글) + 후리가나 + 노션 기록 + 메모 앱 + MD + EPUB
# 사용법: ./whisper_series_stream.sh [영상 폴더 경로]  (생략하면 현재 폴더)
#
# 필요 시크릿(macOS 키체인, 평문 하드코딩 금지):
#   security add-generic-password -a "$USER" -s "jp_subtitle_notion_token" -w "<노션 통합 토큰>" -U
#   security add-generic-password -a "$USER" -s "jp_subtitle_freeimage_key" -w "<freeimage.host API 키>" -U

TARGET_DIR="${1:-.}"
TARGET_PATH=$(cd "$TARGET_DIR" && pwd)
TEMP_SCRIPT="$HOME/whisper_series_stream_run.sh"

/opt/anaconda3/bin/python3 -m pip install requests pykakasi --quiet --disable-pip-version-check 2>/dev/null

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
VALID_FILES=(*.(mp4|webm|mkv|mov)(N))

if [[ ${#VALID_FILES[@]} -eq 0 ]]; then
    echo "⚠️  처리할 영상 파일이 없습니다."
    exit 0
fi

echo "📋 발견된 영상 ${#VALID_FILES[@]}개: ${VALID_FILES[@]}"

for FILENAME in "${VALID_FILES[@]}"; do
    FILENAME_NO_EXT="${FILENAME%.*}"

    echo "\n\033[1;33m========================================\033[0m"
    echo "\033[1;33m🎬 영상 처리 시작: $FILENAME\033[0m"
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
                --prompt "일본어, 대사, 한자, 후리가나" > /dev/null 2>&1
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
import os, sys, re, requests, time, base64, subprocess, warnings, shutil
from datetime import datetime

warnings.filterwarnings("ignore", category=DeprecationWarning)
from pykakasi import kakasi
kks = kakasi()

# ── 시크릿은 코드에 하드코딩하지 않고 macOS 키체인에서 읽는다 ──────────
# 등록: security add-generic-password -a "$USER" -s "jp_subtitle_notion_token" -w "<토큰>" -U
#       security add-generic-password -a "$USER" -s "jp_subtitle_freeimage_key" -w "<키>" -U
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
FREEIMAGE_API_KEY = load_secret("jp_subtitle_freeimage_key")

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

def upload_image(path):
    try:
        with open(path, "rb") as f:
            encoded = base64.b64encode(f.read())
        r = requests.post(
            "https://freeimage.host/api/1/upload",
            data={"key": FREEIMAGE_API_KEY, "action": "upload", "source": encoded},
            timeout=20
        )
        if r.status_code == 200:
            return r.json().get("image", {}).get("url")
    except Exception as e:
        print(f"  ⚠️  업로드 실패: {e}")
    return None

def merge_images(paths, out_path, max_bytes=4 * 1024 * 1024):
    n = len(paths)
    if n == 0:
        return False
    per_width, height = 480, 270
    if n == 1:
        subprocess.run(["ffmpeg", "-y", "-i", paths[0],
                        "-vf", f"scale={per_width}:{height}", "-q:v", "5", out_path],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        fp = "".join(f"[{i}:v]scale={per_width}:{height}[v{i}];" for i in range(n))
        si = "".join(f"[v{i}]" for i in range(n))
        fc = f"{fp}{si}hstack=inputs={n}"
        ia = []
        for p in paths:
            ia += ["-i", p]
        subprocess.run(["ffmpeg", "-y"] + ia + ["-filter_complex", fc, "-q:v", "5", out_path],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    if not os.path.exists(out_path):
        return False

    for quality in [10, 15, 20]:
        if os.path.getsize(out_path) <= max_bytes:
            break
        subprocess.run(["ffmpeg", "-y", "-i", out_path, "-q:v", str(quality),
                        out_path + "_tmp.jpg"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        os.replace(out_path + "_tmp.jpg", out_path)

    if os.path.getsize(out_path) > max_bytes:
        subprocess.run(["ffmpeg", "-y", "-i", out_path,
                        "-vf", "scale=iw/2:ih/2", "-q:v", "15", out_path + "_tmp.jpg"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        os.replace(out_path + "_tmp.jpg", out_path)

    print(f"  📐 병합 이미지: {os.path.getsize(out_path)//1024}KB")
    return True

def concat_audio_clips(clip_paths, out_path):
    if not clip_paths:
        return False
    if len(clip_paths) == 1:
        subprocess.run(["cp", clip_paths[0], out_path])
        return os.path.exists(out_path)
    list_file = out_path + "_list.txt"
    with open(list_file, "w") as f:
        for p in clip_paths:
            f.write(f"file '{os.path.abspath(p)}'\n")
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0",
                    "-i", list_file, "-c", "copy", out_path],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    os.remove(list_file)
    return os.path.exists(out_path)

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
    """EPUB용 CSS — 일본어 황금색 크게, 한국어 회색 작게"""
    css_path = os.path.join(work_dir, "epub_style.css")
    css = """\
body {
    font-family: "Hiragino Kaku Gothic Pro", "ヒラギノ角ゴ Pro", sans-serif;
    background-color: #111111;
    color: #dddddd;
    line-height: 1.8;
    padding: 1em;
}
p.ja {
    font-size: 1.35em;
    font-weight: bold;
    color: #f5c842;
    letter-spacing: 0.05em;
    margin-bottom: 0.1em;
    margin-top: 0.6em;
    text-shadow: 0 0 8px rgba(245,200,66,0.3);
}
p.ko {
    font-size: 0.85em;
    color: #666666;
    margin-top: 0;
    margin-bottom: 0.2em;
    padding-left: 0.5em;
    border-left: 2px solid #333333;
}
img {
    width: 100%;
    border-radius: 6px;
    margin: 0.8em 0;
}
audio {
    width: 100%;
    margin: 0.4em 0 0.8em 0;
    filter: invert(0.8);
}
hr {
    border: none;
    border-top: 1px solid #2a2a2a;
    margin: 1.2em 0;
}
nav#toc a { color: #f5c842; text-decoration: none; }
"""
    with open(css_path, "w", encoding="utf-8") as f:
        f.write(css)
    return css_path

def save_to_md(work_dir, note_title, merged_img_path, ja_list, ko_list,
               concat_wav_path=None, part_num="1", chunk_idx=0):
    base_name  = os.environ.get("FILENAME_NO_EXT", "result")
    result_dir = os.path.join(work_dir, f"{base_name}_work")
    img_dir    = os.path.join(result_dir, "images")
    audio_dir  = os.path.join(result_dir, "audio")
    os.makedirs(img_dir,   exist_ok=True)
    os.makedirs(audio_dir, exist_ok=True)

    img_filename = os.path.basename(merged_img_path)
    if os.path.exists(merged_img_path):
        shutil.copy2(merged_img_path, os.path.join(img_dir, img_filename))

    mp3_tag = ""
    if concat_wav_path and os.path.exists(concat_wav_path):
        mp3_name = f"p{part_num}_{chunk_idx:03d}.mp3"
        mp3_path = os.path.join(audio_dir, mp3_name)
        subprocess.run(
            ["ffmpeg", "-y", "-i", concat_wav_path,
             "-codec:a", "libmp3lame", "-qscale:a", "4", mp3_path],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        if os.path.exists(mp3_path):
            mp3_tag = (
                f'<audio controls="controls">'
                f'<source src="{base_name}_work/audio/{mp3_name}" type="audio/mpeg" />'
                f'</audio>'
            )

    md_path = os.path.join(work_dir, f"{note_title}.md")
    if not os.path.exists(md_path):
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(f"# {note_title}\n\n")

    with open(md_path, "a", encoding="utf-8") as f:
        f.write(f'<img src="{base_name}_work/images/{img_filename}" alt="scene" style="width:100%;" />\n\n')
        if mp3_tag:
            f.write(mp3_tag + "\n\n")
        for ja, ko in zip(ja_list, ko_list):
            furi = generate_furigana(ja)
            f.write(f'<p class="ja">{furi}</p>\n')
            f.write(f'<p class="ko">{ko}</p>\n\n')
        f.write("---\n\n")


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

img_folder = os.path.join(work_dir, f"{base_name}_scenes_part{part_num}")
os.makedirs(img_folder, exist_ok=True)

IMGCAT = next(
    (p for p in ["/opt/homebrew/bin/imgcat", "/usr/local/bin/imgcat"]
     if os.path.exists(p)), None
)

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
    "properties": {"내용": {"title": [{"text": {"content": title}}]}},
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
print(f"🚀 [{base_name}] Notion 연동 완료 │ 총 {len(parsed_lines)}줄 / {TOTAL_SETS}세트\n")

create_epub_css(work_dir)
create_apple_note(note_title)

# ── 3문장씩 처리 ─────────────────────────────────────────────────
for idx in range(0, len(parsed_lines), 3):
    chunk     = parsed_lines[idx:idx + 3]
    chunk_idx = idx // 3 + 1
    n         = len(chunk)

    ja_list = [c['text'] for c in chunk]
    ko_list = [translate(t) for t in ja_list]

    snap_paths = []
    for i, c in enumerate(chunk):
        snap_path = os.path.join(img_folder, f"part{part_num}_{chunk_idx:03d}_{i+1}.jpg")
        if not os.path.exists(snap_path):
            subprocess.run([
                "ffmpeg", "-y",
                "-ss", str(offset_sec + c['start'] + 0.1),
                "-i", video_path,
                "-vframes", "1", "-q:v", "3", snap_path
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if os.path.exists(snap_path):
            snap_paths.append(snap_path)

    merged_path = os.path.join(img_folder, f"part{part_num}_{chunk_idx:03d}_merged.jpg")
    merge_ok    = merge_images(snap_paths, merged_path)

    clip_paths = []
    for i, c in enumerate(chunk):
        clip_start = max(0.0, offset_sec + c['start'] - 0.15)
        clip_dur   = max(0.8, (c['end'] - c['start']) + 0.3)
        clip_path  = os.path.join(work_dir, f"temp_clip_{base_name}_{chunk_idx}_{i+1}.wav")
        subprocess.run([
            "ffmpeg", "-y",
            "-ss", str(clip_start), "-i", video_path,
            "-t", str(clip_dur), "-c:a", "pcm_s16le", clip_path
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if os.path.exists(clip_path):
            clip_paths.append(clip_path)

    concat_path = os.path.join(work_dir, f"temp_concat_{base_name}_{chunk_idx}.wav")
    concat_ok   = concat_audio_clips(clip_paths, concat_path)

    COLORS = ["\033[1;96m", "\033[1;93m", "\033[1;92m"]
    print(f"\033[1;36m{'='*54}\033[0m")
    print(f"\033[1;33m  🎬 {base_name}  {part_num}/{total_parts}편 · 세트 {chunk_idx:03d}\033[0m")
    print(f"\033[1;36m{'='*54}\033[0m")
    if IMGCAT and merge_ok:
        subprocess.run([IMGCAT, "--height", "14", merged_path])
    print(f"\033[1;36m{'--'*27}\033[0m")
    for i in range(n):
        print(f" {COLORS[i]}▶ {ja_list[i]}  →  {ko_list[i]}\033[0m")
    print(f"\033[1;36m{'='*54}\033[0m\n")

    for p in clip_paths:
        if os.path.exists(p): os.remove(p)

    uploaded_url  = upload_image(merged_path) if merge_ok else None
    notion_blocks = build_monitor_blocks(uploaded_url, ja_list, ko_list)
    for i in range(0, len(notion_blocks), 20):
        notion_append(child_url, notion_blocks[i:i+20])
        time.sleep(0.3)

    append_to_apple_note(note_title, ja_list)

    if merge_ok:
        save_to_md(work_dir, note_title, merged_path, ja_list, ko_list,
                   concat_path if concat_ok else None,
                   part_num=part_num, chunk_idx=chunk_idx)

    if concat_ok and os.path.exists(concat_path):
        os.remove(concat_path)

print(f"\n✅ [{base_name}] {part_num}/{total_parts}편 완료 │ {TOTAL_SETS}세트")
PYEOF
        /opt/anaconda3/bin/python3 "$PY_WORKER"
        rm -f "$PY_WORKER"
        echo "✅ [$FILENAME_NO_EXT] 제 $PART편 완료."
    done

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

    COVER_FILE="${WORKING_DIR}/${FILENAME_NO_EXT}_work/cover.jpg"
    FIRST_IMG=$(find "${WORKING_DIR}/${FILENAME_NO_EXT}_work/images" \
        -name "*_merged.jpg" 2>/dev/null | sort | head -1)

    if [[ -n "$FIRST_IMG" && -f "$FIRST_IMG" ]]; then
        cp "$FIRST_IMG" "$COVER_FILE"
        echo "🎨 표지 준비 완료"
    else
        COVER_FILE=""
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
done

echo "\n=================================================="
echo "🎉 모든 영상 처리 완료!"
echo "=================================================="
osascript -e 'display notification "모든 영상 처리 완료!" with title "LanguageStudy ✅"'
afplay /System/Library/Sounds/Glass.aiff
sleep 2
EOF

chmod +x "$TEMP_SCRIPT"

# ── 새 터미널 창에서 실행 ────────────────────────────────────────────
# ★ 2026-07-23: 원래 iTerm을 `tell application "iTerm" ...`으로 제어했는데,
#   이건 macOS 자동화(Automation) 권한이 필요하고, 이 스크립트가 메뉴바 앱
#   (launchd 백그라운드 프로세스) 등에서 호출되면 권한 팝업 자체가 안 떠서
#   조용히 실패한다 (shift_alarm 프로젝트의 이북리더에서 겪은 것과 동일한
#   문제 — 그쪽 README 8-1 참조). 대신 실행 가능한 .command 파일을 만들고
#   `open`으로 여는 방식으로 바꿨다 — 권한이 전혀 필요 없고, iTerm이 없는
#   환경에서도 기본 Terminal.app으로 항상 동작한다.
LAUNCHER="/tmp/_whisper_series_launch.command"
cat > "$LAUNCHER" <<LAUNCHEREOF
#!/bin/zsh
export WORKING_DIR='$TARGET_PATH'
zsh "$TEMP_SCRIPT"
rm -f "$TEMP_SCRIPT"
LAUNCHEREOF
chmod +x "$LAUNCHER"
open -a Terminal "$LAUNCHER"
