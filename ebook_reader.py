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
import os, subprocess, sys, time, signal, json, webbrowser, asyncio
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
TMP_AUDIO = "/tmp/tts_chunk.mp3"

# --- [진행 상태 공유 파일] (shift_alarm.py 메뉴에서 "이어서 읽기"용) ---
LAST_STATE_FILE = os.path.expanduser("~/.ebook_reader_last.json")

FILE_PATH = sys.argv[1]
FILE_NAME = os.path.basename(FILE_PATH)
PROGRESS_FILE = f"{os.path.splitext(FILE_PATH)[0]}.progress"
read_buffer = []
start_page_val = 0
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

def upload_bundle_to_notion(all_text, s_p):
    if not all_text:
        print_status("⚠️  읽은 내용이 없어 전송을 취소합니다.", YELLOW)
        return
    if not NOTION_TOKEN:
        print_status("❌  노션 토큰을 키체인에서 찾을 수 없어 전송을 취소합니다.", ORANGE)
        return

    print_status("☁️  번역 및 노션 전송 시작...", CYAN)
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }
    today = time.strftime("%Y-%m-%d")
    combined_text = "\n\n".join(all_text).strip()

    try:
        translator = Translator()
        translated = translator.translate(combined_text[:2800], src='en', dest='ko')
        ko_text = translated.text
        print_status("✅  번역 완료!", GREEN)
    except:
        ko_text = "번역 지연으로 원문만 저장됨."
        print_status("❌  번역 실패", ORANGE)

    query_url = f"https://api.notion.com/v1/databases/{DATABASE_ID}/query"
    page_id = None
    try:
        res = requests.post(query_url, headers=headers, json={"filter": {"property": TITLE_COL, "title": {"equals": f"📚 {FILE_NAME}"}}})
        results = res.json().get("results")
        if results: page_id = results[0]["id"]
    except: pass

    new_blocks = [
        {"object": "block", "type": "heading_2", "heading_2": {"rich_text": [{"text": {"content": f"📅 {today} 학습 (P.{s_p}~)"}}]}},
        {"object": "block", "type": "callout", "callout": {"rich_text": [{"text": {"content": f"🇺🇸 [Original]\n\n{combined_text[:1900]}"}}], "icon": {"emoji": "📖"}, "color": "gray_background"}},
        {"object": "block", "type": "toggle", "toggle": {"rich_text": [{"text": {"content": "🇰🇷 한국어 번역본 (클릭)"}}], "color": "blue_background", "children": [
            {"object": "block", "type": "paragraph", "paragraph": {"rich_text": [{"text": {"content": ko_text[:1900]}}]}}
        ]}},
        {"object": "block", "type": "divider", "divider": {}}
    ]

    try:
        if page_id:
            print_status("♻️  기존 페이지에 추가 중...", CYAN)
            res = requests.patch(f"https://api.notion.com/v1/blocks/{page_id}/children", headers=headers, json={"children": new_blocks})
        else:
            print_status("🆕  새 페이지 생성 중...", CYAN)
            payload = {
                "parent": {"database_id": DATABASE_ID},
                "properties": {
                    TITLE_COL: {"title": [{"text": {"content": f"📚 {FILE_NAME}"}}]},
                    DATE_COL: {"date": {"start": today}},
                    PAGE_COL: {"rich_text": [{"text": {"content": f"P.{s_p} ~"}}]}
                },
                "children": new_blocks
            }
            res = requests.post("https://api.notion.com/v1/pages", headers=headers, json=payload)

        if res.status_code in [200, 201]:
            print_status("🚀  노션 저장 성공!", GREEN)
            webbrowser.open(f"https://www.notion.so/{DATABASE_ID.replace('-', '')}")
        else:
            print_status(f"❌  노션 에러: {res.status_code}", ORANGE)
    except Exception as e:
        print_status(f"❌  오류: {e}", ORANGE)

def signal_handler(sig, frame):
    global is_exiting
    if is_exiting: return
    is_exiting = True
    print(f"\n\n{YELLOW}{BOLD}  ⏹  학습을 종료합니다...{RESET}\n")
    upload_bundle_to_notion(read_buffer, start_page_val)
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
    global read_buffer, start_page_val

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

if __name__ == "__main__":
    main()
