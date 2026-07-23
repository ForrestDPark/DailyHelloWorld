# 교대근무 메뉴바 앱 (shift_alarm.py)

이 문서는 **새 세션(다른 기기·다른 클라이언트 포함)에서도 이전 대화 맥락 없이 바로 이어서 작업할 수 있도록** `shift_alarm.py` / `ebook_reader.py`에 지금까지 쌓인 기능과 확정 규칙을 전부 기록해둔 것이다. 손자병법 파이프라인 README(`손자병법/README.md`)와 같은 목적.

- 로컬 경로: `/Users/forrestdpark/Desktop/PDG/DailyHelloWorld_/shift_alarm/shift_alarm.py` (관련 파일 전부 `shift_alarm/` 폴더 안 — 손자병법 파이프라인이 `손자병법/` 폴더를 쓰는 것과 같은 패턴)
- **실행 방식(★ 2026-07-23 확정): `~/Library/LaunchAgents/com.shiftalarm.menubar.plist`로 등록된 LaunchAgent다** (로그인 시 자동 시작, `RunAtLoad=true`). 코드 수정 후 재시작은 `nohup`이 아니라 `launchctl kickstart -k gui/$(id -u)/com.shiftalarm.menubar`로 한다 (기존 프로세스 kill + 재시작을 한 번에 처리). **주의: plist의 `ProgramArguments` 경로는 `shift_alarm.py` 파일을 옮기면 반드시 같이 수정해야 한다** — 코드 안 `__file__` 기준 상대경로와 달리 plist 진입점은 절대경로 고정이라 자동으로 안 따라가고, 이미 떠 있는 프로세스는 멀쩡히 돌다가 다음 재부팅/재로드 때(즉 "껐다 켤 때") 그제서야 조용히 실패한다(자세한 사례는 8-1 참조).
- 사용자는 3교대(Day/Swing/GY) + 휴무로 도는 D조 근무자.

---

## 1. 근무표 데이터

- `d_team_schedule_2026.json` — 날짜(`YYYY-MM-DD`) → 근무 코드(`D`/`S`/`G`/`휴`) 매핑. 엑셀 근무표에서 추출. git으로 추적됨(클라우드 자동화 등 다른 환경에서도 오늘 근무를 판단할 수 있어야 해서 저장소에 포함시킴) — `shift_alarm/` 폴더 안, 스크립트와 같은 위치.
- 코드 매핑: `D`→Day, `S`→Swing, `G`→GY(야간), `휴`→휴무.
- 실제 근무 시간 (`SHIFT_WORK_HOURS`): Day 06:00-14:00 / Swing 14:00-22:00 / GY 22:00-06:00(자정 넘어감).
- 근무표 패턴: 휴무 2일 + 근무 6일 반복이 기본이지만, 실제로는 1일/2일/4일짜리 휴무 블록이 섞여있음(연 1일×10회, 2일×35회, 4일×3회) — 로직 짤 때 "휴무는 항상 2일"이라고 가정하면 안 됨.

## 2. 알람(기상) 시간 — `SHIFT_TIMES`
근무 시작 전 깨워주는 알람. macOS `launchd` plist(`~/Library/LaunchAgents/com.shfitalarm.music.plist`)로 등록되며, 울릴 때 `~/Library/Scripts/shift_alarm_run.sh`가 실행되어 Elmedia로 음악 폴더를 열고 "아침루틴음악재생" 단축어(유튜브 랜덤 음악)를 실행함.

| 근무 | 알람 시각 |
|---|---|
| Day | 02:55 |
| Swing | 08:30 |
| GY | 16:30 |

메뉴에서 근무별 알람 시간을 바꿀 수 있고(`⚙️ 알람 시간 설정`), 바뀐 값은 `~/.shift_alarm_config.json`의 `shift_times`에 저장되어 다음 실행에도 유지됨.

## 3. 급여 실시간 표시
- 급여명세서 역산 통상시급(`HOURLY_WAGE = 14861`) 기준. GY는 야간수당 50% 가산(`SHIFT_WAGE_MULTIPLIER`).
- 메뉴바 타이틀에 반올림된 금액(`12만` 식, 소수점 없음)으로 표시. "예정" 문구는 안 붙임.
- **연차 등 근무표와 다르게 수동으로 오늘 근무를 바꾼 경우**(메뉴에서 직접 근무 선택 → `auto_mode` 꺼짐), 급여 계산도 그 수동값을 따라간다 (`today_override` 파라미터로 근무표 대신 config의 `current_shift`를 씀) — 알람만 꺼지고 급여는 근무표 기준으로 계속 올라가던 버그를 고친 것.

## 4. 메뉴바 타이틀 구성
`{근무코드} {급여} {오늘의 리마인더 이모지} {날씨 아이콘}` 형태로 표시 (예: `S 12만 🏋️ ☀️`).
- 날씨 아이콘: 강수확률 기준 ☀️(20% 미만) / ⛅(20~50%) / 🌧️(50%+). Open-Meteo API, 아산시 좌표(`LATITUDE=36.78, LONGITUDE=127.00`) 사용.

## 5. 주간/월간 리마인더 (`REMINDERS`)
교대근무자라 요일이 계속 바뀌므로, 요일이 아니라 근무표의 **"휴무 블록"** 을 기준으로 판단한다. 메뉴의 `🔔 리마인더 켜기/끄기`에서 항목별로 개별 on/off 가능 (`~/.shift_alarm_config.json`의 `reminders_enabled`에 저장).

| 항목 | 조건 |
|---|---|
| 🏋️ 헬스장 가는 날 | 주 2회: 휴무 블록 **첫날** + 그로부터 **이틀 뒤**(보통 복귀 첫 근무일). 단, 그날 "근무 끝나고" 가는 시각에 헬스장이 닫혀있으면 스킵 (아래 6번 참조) |
| 📞 엄마한테 전화 | 휴무 블록 첫날 |
| 🧹 카톡 정리 | 휴무 블록 마지막날 |
| 🛍️ 아울렛 쇼핑 | 월 1회: 그 달의 **첫 번째** 휴무 블록 시작일 |
| 🚶 2만보 걷는 날 | 주 1회: 휴무 블록 **마지막날**. 헬스장 날과 같은 날이 되면(휴무 1일뿐인 주) 그 주는 건너뜀 — 절대 겹치지 않게 |

당일 해당하는 리마인더는 앱 시작 시 1회 + 매일 자정 넘어갈 때 1회, macOS 알림(`rumps.notification`)으로 뜨고, 메뉴바 드롭다운에도 `🔔 오늘: ...` 항목으로 표시됨.

## 6. 헬스장 운영시간 (`is_gym_open`, `_gym_time_ok`)
사용자가 다니는 헬스장은 평일(월~금) 24시간, **토/일요일만 06:00~17:00**로 제한 운영. "근무 끝나고 헬스장 간다"는 전제로, 헬스장 리마인더 후보일마다 **그날 근무가 끝나는 실제 시각**(GY처럼 자정을 넘기면 다음날 새벽 시각)에 헬스장이 열려있는지 체크한다. 휴무일(근무 없음)이면 시간 제약 없이 통과. 닫혀있으면(주로 주말 저녁 퇴근하는 Swing 근무) 그날은 헬스장 리마인더를 아예 띄우지 않는다.

## 7. 전자제품 전원 끄기 알람 (`ELECTRONICS_OFF_TIMES`)
근무 끝나고 자는 시간대에 맞춰, 근무별로 하루 한 번 "전자제품 꺼라" 알림.

| 근무 | 시각 |
|---|---|
| Day | 17:00 |
| GY | 08:00 |
| Swing | 23:50 |

휴무일엔 알림 없음. 1분 주기 타이머(`_check_electronics_off`)로 현재 `current_shift` 기준 시각 일치 여부를 체크, 하루 한 번만 발송.

**참고 (다른 자동화 설계 시 사용할 값):** 사용자는 보통 퇴근 후 4~5시간 뒤에는 잠들어있다고 함 → Day는 약 18:30~19:00, Swing은 약 02:30~03:00(다음날), GY는 약 10:30~11:00 이 "확실히 자고 있을 시간"의 기준점.

## 8. 아침 학습 — ebook_reader.py (PDF/EPUB TTS 낭독 + 노션 기록)
- `ebook_reader.py`: PDF/EPUB를 문장 단위로 잘라 edge-tts(영어 음성, `en-US-JennyNeural`, 속도 -10%)로 낭독. 원래 macOS 단축어로 실행하던 것을 shift_alarm.py 메뉴로 옮김.
- **노션 토큰은 코드에 하드코딩하지 않고 macOS 키체인에서 읽음**: `security find-generic-password -a "$USER" -s "ebook_reader_notion_token" -w`. 토큰 등록/갱신: `security add-generic-password -a "$USER" -s "ebook_reader_notion_token" -w "<token>" -U`.
- 노션 저장 성공해도 **브라우저 자동 오픈은 안 함** (브라우저 로그인 계정이 워크스페이스 계정과 달라서 "권한 없음" 오탐 뜨는 문제 때문에 제거함 — 저장 자체는 터미널에 "🚀 노션 저장 성공!"으로 확인).
- 진행 상황은 **TTS 재생 시작 전에** 저장한다(재생 끝난 후 저장하면 재생 중 Ctrl+C로 끌 때 기록이 안 남는 버그가 있었음).
- 마지막으로 읽던 책 정보는 `~/.ebook_reader_last.json`에 기록(`file`, `file_name`, `page`, `idx`, `total`).
- **메뉴바 통합**: 팝업이 아니라 실제 메뉴 항목으로 노출.
  - `📖 이어하기: {책이름 14자로 축약+...} (P.페이지)` — 마지막 읽던 책이 있을 때만 표시, 클릭하면 바로 이어서 실행.
  - `📖 다른 책 선택해서 읽기` — 항상 표시, macOS 파일선택 다이얼로그(pdf/epub)로 새 책 선택.
- 실행되면 새 터미널 창이 뜨는데: 검정 배경+초록 글씨, 폰트 크기 28(원래 20에서 1.4배), 창은 `zoomed`(전체창), 실행 시 맥 시스템 볼륨을 80%로 설정.

### 8-1. ★★ 터미널 창이 안 뜨거나 스타일이 안 먹는 문제 (2026-07-23, 근본 원인 확정)

**증상**: `이어하기`/`다른 책 선택` 메뉴를 눌러도 아무 반응이 없거나(창 자체가 안 뜸), 창은 뜨는데 스타일링(검정 배경/초록 글씨/폰트 28/전체화면)이 하나도 안 먹음.

**근본 원인 — launchd로 뜨는 백그라운드 프로세스는 macOS 자동화(Automation, `kTCCServiceAppleEvents`) 권한을 절대 얻을 수 없다.**
- 예전 코드는 `open_ebook_reader_terminal()`이 `tell application "Terminal" ... do script`로 새 창을 열고 스타일까지 한 번에 처리했다. 이 방식은 "Terminal을 제어할 권한"이 필요한데, 이 권한은 macOS가 **화면에 팝업을 띄워서 사용자가 직접 '허용'을 눌러야만** 부여된다.
- `shift_alarm.py`는 `~/Library/LaunchAgents/com.shiftalarm.menubar.plist`로 등록된 LaunchAgent라서 로그인 시 launchd가 조용히 백그라운드로 띄운다. 이 실행 경로에서는 **권한 팝업 자체가 뜨지 않는다** (Finder 더블클릭이나 Terminal에서 직접 실행한 게 아니라서 macOS가 "책임 프로세스"를 GUI 세션에 제대로 붙이지 못함). 그래서 팝업이 안 뜨고, `system.log`의 TCC 데이터베이스(`~/Library/Application Support/com.apple.TCC/TCC.db`)를 조회해보면 이 python3 바이너리에 대한 권한 기록이 아예 없었다 — "거부됨"도 아니고 "물어본 적조차 없음" 상태. AppleEvent는 그냥 조용히 실패하고, 코드도 그 실패를 체크하지 않아서 사용자 입장에선 그냥 "아무 일도 안 일어남"으로 보였다.
- 참고로 같은 이유로 `com.shiftalarm.menubar.plist`의 경로가 옛날 위치(`shift_alarm.py`를 `shift_alarm/` 서브폴더로 옮기기 전 경로)를 계속 가리키고 있었던 별개의 버그도 있었다 — 이건 "이미 떠 있던 프로세스는 파일이 옮겨져도 계속 잘 돌아가다가, 로그아웃/재부팅 등으로 launchd가 plist를 다시 읽어들이는 순간(즉 '껐다 켜는' 순간) 그제서야 옛 경로를 못 찾아 실패하는" 패턴이라 원인 파악이 헷갈리기 쉽다. plist의 `ProgramArguments` 경로는 스크립트를 옮기면 반드시 같이 고쳐야 한다(코드 안의 `__file__` 기준 상대경로와는 별개로, plist의 진입점 경로는 절대경로로 고정돼 있어서 자동으로 안 따라감).

**해결 (2단계 분리 구조로 재작성됨):**
1. **창을 여는 것(핵심 기능)**: `/tmp/_ebook_reader_launch.command`라는 실행 가능한 셸 스크립트를 만들고 `open -a Terminal <파일>`로 연다. 이건 AppleEvent가 아니라 Launch Services가 문서를 여는 것뿐이라 자동화 권한이 전혀 필요 없다 — **항상 100% 동작을 보장.**
2. **스타일링(배경/폰트/전체화면)**: `shift_alarm/StyleEbookTerminal.app`이라는 별도의 작은 컴파일된 AppleScript 앱(`osacompile`로 빌드)으로 분리했다. `open -a StyleEbookTerminal.app`으로 여는 것도 Launch Services를 통하는 거라 launchd가 직접 부르는 것과 달리 **정상적으로 권한 팝업이 뜬다.** 최초 1회 "Terminal을 제어하도록 허용하시겠습니까?" 팝업에서 허용을 누르면, 그 뒤로는 이 앱 자체(경로 기준)에 영구적으로 권한이 기록되어 launchd가 불러도 계속 스타일링이 적용된다. (2026-07-23 세션에서 최초 실행 시 이미 허용 처리됨 — `TCC.db`에 `StyleEbookTerminal.app/Contents/MacOS/applet`이 `auth_value=2`로 기록된 것 확인.)
3. `open_ebook_reader_terminal()`이 이제 이 두 단계를 순서대로(창 열기 → 스타일링 앱 열기) 실행한다. 스타일링 앱이 없거나 실패해도(`os.path.exists` 체크) 창 열기 자체는 항상 성공한다 — 핵심 기능과 부가 기능(스타일)을 절대 하나의 실패 지점으로 묶지 않는다.

**교훈 (다른 메뉴 항목/미래 자동화에도 적용):** `subprocess.Popen(["osascript", "-e", 'tell application "X" ...'])`을 launchd 백그라운드 앱(rumps 메뉴바 앱 포함) 안에서 직접 호출하는 코드는 전부 이 문제를 안고 있을 수 있다. Elmedia 재생(`open -a "Elmedia Video Player" ...`)처럼 `open`만 쓰는 코드는 안전하지만, `tell application` 형태로 다른 앱을 "제어"하는 AppleScript가 필요하면 반드시 별도 `.app`(`osacompile`)으로 분리해서 `open -a`로 불러야 한다.

## 9. 연차/수동 근무 오버라이드
메뉴에서 근무를 수동으로 선택하면(`auto_mode` 꺼짐), 그 값이 알람뿐 아니라 급여 계산(3번 항목)에도 그대로 반영됨. 연차로 쉬는 날은 메뉴에서 `휴무`를 선택하면 그날 알람도 꺼지고 급여도 "휴무"로 처리됨.

## 10. 🎲 랜덤 추천 사이트 열기 (2026-07-23 추가)
메뉴의 `🎲 추천 사이트 열기 (랜덤 북마크 3개)`를 누르면 크롬 북마크 **전체**(`bookmark_bar`/`other`/`synced` 전 폴더, 특정 폴더로 한정하지 않음)에서 무작위로 3개를 뽑아 크롬으로 연다.
- 로직: `pick_random_bookmarks(n)`이 `~/Library/Application Support/Google/Chrome/Default/Bookmarks`를 직접 읽어 URL만 전부 모은 뒤 `random.sample`로 n개 추출 → `open_random_bookmarks(n)`이 각각 `open -a "Google Chrome" <url>`로 연다(북마크관리 프로젝트의 `fix_bookmarks.py`와 같은 파일 포맷을 읽지만, 여긴 읽기 전용이라 크롬이 켜져있어도 상관없음 — 북마크관리 쪽의 "크롬 켜진 채로 쓰면 덮어써짐" 문제와는 무관).
- 뽑힌 3개 URL은 알림(`rumps.notification`)으로도 보여줌.
- 북마크를 못 읽으면(파일 없음/파싱 실패) "오류" 알럿만 띄우고 아무것도 열지 않음.

## 11. 자잘한 운영 메모
- 코드/설정 변경 후에는 `launchctl kickstart -k gui/$(id -u)/com.shiftalarm.menubar`로 재시작해야 반영됨 (rumps 앱이라 hot-reload 없음; ★ 2026-07-23부터 LaunchAgent 등록 방식으로 바뀌어 `nohup` 방식은 더 이상 안 씀 — 1번 항목 참조). `SCHEDULE_FILE`/`EBOOK_READER_SCRIPT` 등은 `__file__` 기준 상대경로라 폴더 위치가 바뀌어도 코드 수정 없이 그대로 동작하지만, **plist의 `ProgramArguments` 자체는 절대경로라 폴더/파일을 옮기면 별도로 고쳐야 함**(1번 항목 참조).
- `~/Downloads/shift_alarm.py`에도 항상 최신 사본을 동기화해둠 (사용자가 그쪽에서도 참조하는 습관이 있어서).
- 이 저장소(`DailyHelloWorld`)는 shift_alarm 외에도 손자병법 해석 파이프라인 등 전혀 다른 프로젝트들이 같이 들어있는 개인 모음 저장소라, `git status`에 관련 없는 변경사항(다른 폴더의 M/D/??)이 항상 잔뜩 떠 있다 — shift_alarm.py/ebook_reader.py만 `git add`해서 커밋할 것.
- 여러 세션(로컬 CLI + 웹/모바일 "claude remote-control")이 같은 저장소에 동시에 커밋할 수 있으므로, push 전에 `git fetch && git log HEAD..origin/main --oneline`으로 원격에 새 커밋이 있는지 항상 확인하고, 있으면 merge 후 push할 것.
