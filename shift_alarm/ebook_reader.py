#!/usr/bin/env python3
"""
아침 루틴용 PDF/EPUB 리더 (TTS 낭독 + 노션 학습 기록 업로드)
실행: python3 ebook_reader.py <파일경로.pdf|.epub>

- 커피 그라인딩하며 듣는 용도. 문장 단위로 잘라서 edge-tts로 읽어줌.
- Ctrl+C로 종료하면 그때까지 읽은 내용을 번역해서 노션에 저장.
- 노션 토큰은 macOS 키체인에서 읽어온다 (평문 하드코딩 금지):
    security add-generic-password -a "$USER" -s "ebook_reader_notion_token" -w "<token>" -U
- 마지막으로 읽은 파일/페이지는 ~/.ebook_reader_last.json 에 기록해서
  shift_alarm.py 메뉴에서 "이어서 읽기" 여부를 물어볼 때 사용한다.
"""
import os, subprocess, sys, time, signal, json, asyncio, tempfile, uuid
import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup
from googletrans import Translator
import edge_tts
import requests

# --- [노션 설정] ---
NOTION_TOKEN_SERVICE = "ebook_reader_notion_token"
DATABASE_ID = "35932a1eae808015a242d20bd707f7f8"
TITLE_COL = "내용"
DATE_COL = "날짜"
PAGE_COL = "페이지"


def load_notion_token():
    try:
        result = subprocess.run(
            ["security", "find-generic-password", "-a", os.environ.get("USER", ""),
             "-s", NOTION_TOKEN_SERVICE, "-w"],
            capture_output=True, text=True, check=True,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return None


NOTION_TOKEN = load_notion_token()

# --- [TTS 설정] ---
VOICE = "en-US-JennyNeural"
RATE  = "-10%"
TMP_AUDIO = os.path.join(tempfile.gettempdir(), f"ebook_reader_tts_{os.getpid()}.mp3")

# --- [진행 상태 공유 파일] (shift_alarm.py 메뉴에서 "이어서 읽기"용) ---
LAST_STATE_FILE = os.path.expanduser("~/.ebook_reader_last.json")
SESSION_DIR = os.path.expanduser("~/.ebook_reader/sessions")

FILE_PATH = sys.argv[1]
FILE_NAME = os.path.basename(FILE_PATH)
PROGRESS_FILE = f"{os.path.splitext(FILE_PATH)[0]}.progress"
read_buffer = []
start_page_val = 0
end_page_val = 0
is_exiting = False

# ── ANSI 컬러 ──────────────────────────────────────
RESET   = "\033[0m"
BOLD    = "\033[1m"
DIM     = "\033[2m"
GREEN   = "\033[38;5;82m"
CYAN    = "\033[38;5;51m"
YELLOW  = "\033[38;5;226m"
ORANGE  = "\033[38;5;208m"
WHITE   = "\033[38;5;255m"
GRAY    = "\033[38;5;240m"
BG_DARK = "\033[48;5;234m"
BG_BOX  = "\033[48;5;236m"

def clear_line():
    print("\033[2K\033[1G", end="")

def term_width():
    try:
        return os.get_terminal_size().columns
    except:
        return 80

def print_header(file_name):
    w = term_width()
    line = "─" * (w - 2)
    print(f"\n{CYAN}{BOLD}╭{line}╮{RESET}")
    title = f"  📚  {file_name}"
    pad = w - len(title) - 1
    print(f"{CYAN}{BOLD}│{RESET}{WHITE}{BOLD}{title}{' ' * pad}{CYAN}{BOLD}│{RESET}")
    print(f"{CYAN}{BOLD}╰{line}╯{RESET}\n")

def print_progress_bar(current, total, page):
    w = term_width()
    pct = current / total if total else 0
    bar_w = w - 30
    filled = int(bar_w * pct)
    empty  = bar_w - filled

    bar = f"{GREEN}{'█' * filled}{GRAY}{'░' * empty}{RESET}"
    pct_str = f"{pct*100:5.1f}%"
    count_str = f"{current}/{total}"

    print(f"\n{GRAY}  진행 {RESET}{bar} {YELLOW}{BOLD}{pct_str}{RESET}  {DIM}{count_str}{RESET}  {CYAN}P.{page}{RESET}")

def print_sentence_box(text, current, total, page):
    w = term_width()
    inner_w = w - 4

    words = text.split()
    lines = []
    line = ""
    for word in words:
        if len(line) + len(word) + 1 <= inner_w:
            line = (line + " " + word).strip()
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)

    top    = f"{ORANGE}{BOLD}╔{'═' * (w-2)}╗{RESET}"
    bottom = f"{ORANGE}{BOLD}╚{'═' * (w-2)}╝{RESET}"

    print(f"\n{top}")
    for l in lines:
        pad = inner_w - len(l)
        print(f"{ORANGE}{BOLD}║{RESET}  {WHITE}{BOLD}{l}{' ' * pad}  {ORANGE}{BOLD}║{RESET}")
    print(bottom)

def print_status(msg, color=GRAY):
    print(f"\n  {color}{msg}{RESET}")

def save_last_state(page, idx, total):
    try:
        with open(LAST_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "file": os.path.abspath(FILE_PATH),
                "file_name": FILE_NAME,
                "page": page,
                "idx": idx,
                "total": total,
            }, f, ensure_ascii=False)
    except Exception:
        pass

async def speak(text):
    communicate = edge_tts.Communicate(text, VOICE, rate=RATE)
    await communicate.save(TMP_AUDIO)
    proc = subprocess.Popen(["afplay", TMP_AUDIO])
    proc.wait()
    time.sleep(0.2)


def split_text(text, limit=1800):
    """Notion 글자 제한 안에서 원문을 하나도 버리지 않고 순서대로 나눈다."""
    text = text.strip()
    chunks = []
    while text:
        if len(text) <= limit:
            chunks.append(text)
            break
        cut = max(text.rfind("\n", 0, limit), text.rfind(". ", 0, limit))
        if cut < limit // 2:
            cut = limit
        elif text[cut:cut + 2] == ". ":
            cut += 1
        chunks.append(text[:cut].strip())
        text = text[cut:].strip()
    return [chunk for chunk in chunks if chunk]


def translate_all(text):
    """googletrans 요청도 나눠 보내 전체 원문에 대응하는 번역을 만든다."""
    translator = Translator()
    translated = []
    for chunk in split_text(text, 2800):
        translated.append(translator.translate(chunk, src="auto", dest="ko").text)
    return "\n\n".join(translated)


def save_local_session(original, translated, start_page, end_page, notion_status):
    """Notion 성공 여부와 무관하게 매일 읽은 원문·번역을 로컬 JSON으로 보존한다."""
    os.makedirs(SESSION_DIR, exist_ok=True)
    session_id = time.strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:8]
    path = os.path.join(SESSION_DIR, f"{session_id}.json")
    record = {
        "schema_version": 1,
        "session_id": session_id,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "book_file": os.path.abspath(FILE_PATH),
        "book_name": FILE_NAME,
        "start_page": start_page,
        "end_page": end_page,
        "original": original,
        "translation_ko": translated,
        "notion_status": notion_status,
    }
    with open(path, "w", encoding="utf-8") as file:
        json.dump(record, file, ensure_ascii=False, indent=2)
    return path, record


def update_local_session(path, record, **changes):
    record.update(changes)
    with open(path, "w", encoding="utf-8") as file:
        json.dump(record, file, ensure_ascii=False, indent=2)


TULPACHAT_WORKER_KEYCHAIN_SERVICE = "com.forrest.tulpachat.worker"
TULPACHAT_POST_MESSAGE_URL = "http://127.0.0.1:8000/api/worker/post_message"
EBOOK_TULPACHAT_PERSONA_NAME = "독서지기"
# ★ 2026-08-30: "노션에 정리해온 내용을 바탕으로 독서 방에 저자를 페르소나화해서
# 초대한다음 같이 토론하면 좋겠어"는 요청 — "독서지기"의 1:1 방 대신, 저자
# 페르소나(현재는 Tools of Titans의 티모시 페리스)도 함께 초대해둔 전용
# custom_rooms 방으로 옮겼다(손자병법 토론방과 같은 패턴). 읽는 책이 바뀌면
# 이 방에 새 저자를 초대하고 이 room_id는 그대로 재사용하면 된다.
EBOOK_DISCUSSION_ROOM_ID = "custom_8213ad5b05"


def notify_tulpachat_reading_done():
    """★ 2026-08-30: "ebook reader도 페르소나화해서 매일 읽고 나면 페르소나
    채팅방에서 오늘 무슨 내용 읽었는지 간단하게 토론하면 좋겠어"는 요청 —
    방금 저장한 세션(가장 최근 파일)을 읽어 '독서지기' 페르소나 명의로 독서
    토론방(EBOOK_DISCUSSION_ROOM_ID)에 짧게 알린다. 툴파챗 서버가 안 떠
    있거나 키체인 토큰이 없어도 조용히 넘어간다(이북 리더 종료 자체를 막으면
    안 됨)."""
    try:
        files = sorted(
            (os.path.join(SESSION_DIR, name) for name in os.listdir(SESSION_DIR)),
            key=os.path.getmtime,
        )
        if not files:
            return
        with open(files[-1], encoding="utf-8") as f:
            record = json.load(f)
    except (OSError, ValueError, IndexError):
        return
    book = record.get("book_name", "책")
    start = record.get("start_page")
    end = record.get("end_page")
    content = (
        f"📖 오늘 {book} {start}~{end}페이지 읽었더라!\n"
        "오늘 읽은 내용 궁금하면 말 걸어, 같이 얘기해보자."
    )
    try:
        result = subprocess.run(
            ["security", "find-generic-password", "-s", TULPACHAT_WORKER_KEYCHAIN_SERVICE, "-w"],
            capture_output=True, text=True, check=True, timeout=10,
        )
        token = result.stdout.strip()
        requests.post(
            TULPACHAT_POST_MESSAGE_URL,
            json={
                "persona_name": EBOOK_TULPACHAT_PERSONA_NAME,
                "room_id": EBOOK_DISCUSSION_ROOM_ID,
                "content": content,
            },
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
    except Exception:
        pass


def notion_paragraphs(text, prefix=""):
    blocks = []
    for index, chunk in enumerate(split_text(text), 1):
        label = f"{prefix} {index}\n" if prefix else ""
        blocks.append({
            "object": "block",
            "type": "paragraph",
            "paragraph": {"rich_text": [{"text": {"content": label + chunk}}]},
        })
    return blocks


def append_notion_blocks(page_id, headers, blocks):
    """Notion의 요청당 children 100개 제한을 지키며 전부 추가한다."""
    for index in range(0, len(blocks), 100):
        response = requests.patch(
            f"https://api.notion.com/v1/blocks/{page_id}/children",
            headers=headers,
            json={"children": blocks[index:index + 100]},
            timeout=30,
        )
        response.raise_for_status()

def upload_bundle_to_notion(all_text, s_p, e_p):
    if not all_text:
        print_status("⚠️  읽은 내용이 없어 전송을 취소합니다.", YELLOW)
        return
    today = time.strftime("%Y-%m-%d")
    combined_text = "\n\n".join(all_text).strip()

    try:
        ko_text = translate_all(combined_text)
        print_status("✅  번역 완료!", GREEN)
    except Exception as error:
        ko_text = ""
        print_status(f"⚠️  번역 실패 — 원문은 보존합니다: {error}", ORANGE)

    local_path, local_record = save_local_session(
        combined_text, ko_text, s_p, e_p, "pending" if NOTION_TOKEN else "token_missing"
    )
    print_status(f"💾  로컬 학습 기록 저장: {local_path}", GREEN)

    if not NOTION_TOKEN:
        print_status("⚠️  노션 토큰이 없어 로컬에만 저장했습니다.", YELLOW)
        return

    print_status("☁️  노션 전송 시작...", CYAN)
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }

    query_url = f"https://api.notion.com/v1/databases/{DATABASE_ID}/query"
    page_id = None
    try:
        res = requests.post(query_url, headers=headers, json={"filter": {"property": TITLE_COL, "title": {"equals": f"📚 {FILE_NAME}"}}}, timeout=30)
        res.raise_for_status()
        results = res.json().get("results", [])
        if results: page_id = results[0]["id"]
    except Exception as error:
        update_local_session(local_path, local_record, notion_status="query_failed", notion_error=str(error))
        print_status(f"❌  노션 조회 실패: {error}", ORANGE)
        return

    new_blocks = [
        {"object": "block", "type": "heading_2", "heading_2": {"rich_text": [{"text": {"content": f"📅 {today} 학습 (P.{s_p}~P.{e_p})"}}]}},
        {"object": "block", "type": "heading_3", "heading_3": {"rich_text": [{"text": {"content": "📖 원문"}}]}},
    ]
    new_blocks.extend(notion_paragraphs(combined_text, "Original"))
    if ko_text:
        new_blocks.append({"object": "block", "type": "heading_3", "heading_3": {"rich_text": [{"text": {"content": "🇰🇷 한국어 번역"}}]}})
        new_blocks.extend(notion_paragraphs(ko_text, "번역"))
    new_blocks.append({"object": "block", "type": "divider", "divider": {}})

    try:
        if page_id:
            print_status("♻️  기존 페이지에 추가 중...", CYAN)
            append_notion_blocks(page_id, headers, new_blocks)
        else:
            print_status("🆕  새 페이지 생성 중...", CYAN)
            payload = {
                "parent": {"database_id": DATABASE_ID},
                "properties": {
                    TITLE_COL: {"title": [{"text": {"content": f"📚 {FILE_NAME}"}}]},
                    DATE_COL: {"date": {"start": today}},
                    PAGE_COL: {"rich_text": [{"text": {"content": f"P.{s_p} ~"}}]}
                },
                "children": []
            }
            res = requests.post("https://api.notion.com/v1/pages", headers=headers, json=payload, timeout=30)
            res.raise_for_status()
            page_id = res.json()["id"]
            append_notion_blocks(page_id, headers, new_blocks)

        update_local_session(local_path, local_record, notion_status="uploaded", notion_page_id=page_id)
        print_status("🚀  노션 저장 성공! 원문과 번역을 모두 보존했습니다.", GREEN)
    except Exception as e:
        update_local_session(local_path, local_record, notion_status="upload_failed", notion_error=str(e))
        print_status(f"❌  오류: {e}", ORANGE)

def signal_handler(sig, frame):
    global is_exiting
    if is_exiting: return
    is_exiting = True
    print(f"\n\n{YELLOW}{BOLD}  ⏹  학습을 종료합니다...{RESET}\n")
    upload_bundle_to_notion(read_buffer, start_page_val, end_page_val or start_page_val)
    if read_buffer:
        notify_tulpachat_reading_done()
    try:
        os.remove(TMP_AUDIO)
    except OSError:
        pass
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

def extract_sentences(path):
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext == ".pdf":
            import fitz
            doc = fitz.open(path)
            full_text = []
            for p_num, page in enumerate(doc):
                text = page.get_text("text")
                if not text: continue
                for l in text.split('\n'):
                    if l.strip():
                        full_text.append({"p": p_num+1, "t": l.strip()})
            return full_text
        elif ext == ".epub":
            book = epub.read_epub(path)
            full_text = []
            p_num = 0
            for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
                soup = BeautifulSoup(item.get_content(), 'html.parser')
                for tag in soup.find_all(['p', 'h1', 'h2', 'h3']):
                    text = tag.get_text().strip()
                    if text:
                        p_num += 1
                        full_text.append({"p": p_num, "t": text})
            return full_text
        else:
            print_status(f"❌  지원하지 않는 형식: {ext}", ORANGE)
            return []
    except Exception as e:
        print_status(f"❌  파일 열기 오류: {e}", ORANGE)
        return []

def combine_into_sentences(line_data_list):
    sentences = []
    temp_text = ""
    temp_pages = set()

    for data in line_data_list:
        line = data['t'].strip()
        temp_pages.add(data['p'])

        if temp_text.endswith('-'):
            temp_text = temp_text[:-1] + line
        else:
            temp_text = (temp_text + " " + line).strip()

        if any(temp_text.endswith(p) for p in ['.', '!', '?', '."', '!"', '?"']):
            sentences.append({"pages": sorted(list(temp_pages)), "content": temp_text})
            temp_text = ""
            temp_pages = set()

    if temp_text.strip():
        sentences.append({"pages": sorted(list(temp_pages)), "content": temp_text.strip()})

    return sentences

def main():
    global read_buffer, start_page_val, end_page_val

    os.system("clear")
    print_header(FILE_NAME)

    all_sentences = combine_into_sentences(extract_sentences(FILE_PATH))
    if not all_sentences:
        print_status("❌  텍스트를 추출할 수 없습니다.", ORANGE)
        return

    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, 'r') as f:
            last_idx = int(f.read().strip())
        last_page = all_sentences[min(last_idx, len(all_sentences)-1)]['pages'][0]
        print_status(f"📖  이전 학습 위치: {last_idx}번째 문장  (P.{last_page} 부근)", CYAN)
    else:
        last_idx = 0
        print_status("🆕  처음 학습하는 파일입니다.", GREEN)

    print(f"\n  {YELLOW}👉  시작할 페이지 번호 입력  (엔터 = 이어서){RESET}  ", end="")
    target = input().strip()

    start_idx = last_idx
    if target.isdigit():
        target_page = int(target)
        for i, sent in enumerate(all_sentences):
            if any(p >= target_page for p in sent['pages']):
                start_idx = i
                break

    to_read = all_sentences[start_idx:]
    if not to_read:
        print_status("✅  모든 내용을 이미 학습했습니다!", GREEN)
        return

    start_page_val = to_read[0]['pages'][0]
    total = len(all_sentences)

    print_status(f"🎙️   음성: {VOICE}   속도: {RATE}", GRAY)
    print_status(f"🚀  P.{start_page_val} 부터 시작  |  총 {len(to_read)}문장 남음  |  Ctrl+C = 저장 후 종료", GREEN)

    for i, data in enumerate(to_read):
        current_idx = start_idx + i
        page = data['pages'][0]
        end_page_val = data['pages'][-1]

        os.system("clear")
        print_header(FILE_NAME)
        print_progress_bar(current_idx + 1, total, page)
        print_sentence_box(data['content'], current_idx + 1, total, page)

        # 재생 시작 "전에" 저장해둬야, 재생 중 Ctrl+C로 꺼도 진행 상황이 남는다.
        with open(PROGRESS_FILE, 'w') as f:
            f.write(str(current_idx + 1))
        save_last_state(page, current_idx + 1, total)

        read_buffer.append(data['content'])
        asyncio.run(speak(data['content']))

    upload_bundle_to_notion(read_buffer, start_page_val, end_page_val)
    try:
        os.remove(TMP_AUDIO)
    except OSError:
        pass

if __name__ == "__main__":
    main()
