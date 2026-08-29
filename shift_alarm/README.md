# 교대근무 메뉴바 앱 (shift_alarm.py)

이 문서는 **새 세션(다른 기기·다른 클라이언트 포함)에서도 이전 대화 맥락 없이 바로 이어서 작업할 수 있도록** `shift_alarm.py` / `ebook_reader.py`에 지금까지 쌓인 기능과 확정 규칙을 전부 기록해둔 것이다. 손자병법 파이프라인 README(`손자병법/README.md`)와 같은 목적.

- 로컬 경로: `/Users/forrestdpark/Desktop/PDG/DailyHelloWorld_/shift_alarm/shift_alarm.py` (관련 파일 전부 `shift_alarm/` 폴더 안 — 손자병법 파이프라인이 `손자병법/` 폴더를 쓰는 것과 같은 패턴)
- **실행 방식(★ 2026-07-23 확정): `~/Library/LaunchAgents/com.shiftalarm.menubar.plist`로 등록된 LaunchAgent다** (로그인 시 자동 시작, `RunAtLoad=true`). 코드 수정 후 재시작은 `nohup`이 아니라 `launchctl kickstart -k gui/$(id -u)/com.shiftalarm.menubar`로 한다 (기존 프로세스 kill + 재시작을 한 번에 처리). **주의: plist의 `ProgramArguments` 경로는 `shift_alarm.py` 파일을 옮기면 반드시 같이 수정해야 한다** — 코드 안 `__file__` 기준 상대경로와 달리 plist 진입점은 절대경로 고정이라 자동으로 안 따라가고, 이미 떠 있는 프로세스는 멀쩡히 돌다가 다음 재부팅/재로드 때(즉 "껐다 켤 때") 그제서야 조용히 실패한다(자세한 사례는 8-1 참조).

### Shift Alarm Pet (2026-08-29)

메뉴바가 노치나 다른 상태 항목에 밀려 숨는 경우에도 근무·날씨와 Codex/Claude 사용량을 볼 수 있도록 투명한 플로팅 Pet을 함께 띄운다. 기존 메뉴바는 fallback 및 전체 기능 메뉴로 유지한다.

- Pet 이미지 클릭(말풍선이나 빈 공간은 반응 없음, ★ 2026-08-29 53번 항목): 살짝 커졌다 줄어드는 팝 애니메이션과 함께, 메뉴바 아이콘을 눌렀을 때와 완전히 같은 NSMenu(rumps가 관리하는 실제 메뉴)가 Pet 바로 위에 뜬다 — 그 안의 모든 항목이 그대로 클릭 가능. "현재 설정 확인"은 그 메뉴의 `기타` 하위메뉴에 그대로 남아있다.
- Pet 드래그(이미지·말풍선 어디서 시작해도 동작): 위치 이동 및 `~/.shift_alarm_config.json`에 좌표 저장
- Pet 우클릭: 숨김
- 배경 없는 이미지 + 꼬리 달린 말풍선(alpha 0.55) 구조(★ 2026-08-29 53번 항목) — 말풍선 안 텍스트는 근무·저장공간·오늘 리마인더·AI 사용량[·열 상태] 카드를 30초 간격으로 자동 순환 표시한다.
- 메뉴바 `기타 → 🐾 Shift Pet 표시/숨기기`: 숨긴 Pet 복구
- 일반 Space에는 따라오지만 macOS native 전체화면 위에는 억지로 겹치지 않는다.
- `assets/shift_alarm_pet.png`가 있으면 사용하고, 없으면 로봇 이모지를 표시한다.
  - **★ 2026-08-07 KeepAlive 추가**: 예전엔 `KeepAlive: false`라 앱이 정말로 죽으면(크래시 등) launchd가 자동으로 다시 안 띄워줘서, 수동으로 kickstart 해줄 때까지 메뉴바 아이콘이 계속 사라진 채로 남는 문제가 있었다. `KeepAlive: {SuccessfulExit: false}`로 바꿔서 **비정상 종료(크래시/kill)일 때만** 자동 재시작하고, 메뉴의 "종료"로 정상 종료(exit 0, `rumps.quit_application()`)했을 땐 재시작 안 함. `StandardOutPath`/`StandardErrorPath`를 `~/Library/Logs/shift_alarm.{out,err}.log`로 지정해서 다음에 또 죽으면 원인을 사후에 확인할 수 있게 했다. plist를 고친 뒤엔 `launchctl kickstart -k`만으로는 반영이 안 되고(플리스트 자체를 다시 안 읽음) `launchctl bootout gui/$(id -u)/com.shiftalarm.menubar && launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.shiftalarm.menubar.plist`로 재로드해야 한다.
- 사용자는 3교대(Day/Swing/GY) + 휴무로 도는 D조 근무자.

## 0. 메뉴 구성 원칙 (2026-08-13 사용 빈도 기준 재설계)

메인 메뉴 최상단은 매일 확인하는 `오늘 급여·휴무 → 오늘 리마인더 → 메일 → 날씨 → 추천 공고·경진대회 → 추천 사이트 → 손자병법 최신`, 그 아래는 자주 직접 실행하는 `일본어 자막 추출 → 전자책 이어하기 → 좋아요 Elmedia → Elmedia 지금 바로 재생 → Hue 거실 켜기/끄기 → Codex·Claude 사용량 → 저장공간 관리` 순서로 고정한다. 강수확률이 50% 이상이면 날씨 옆에 `(우산 준비하세요)`를 표시한다. Codex는 연보라, Claude는 주황으로 표시하고 각각 임계치를 넘으면 빨강으로 경고한다. 설정·상태·가끔 쓰는 보조 도구는 `기타` 하위 메뉴로 접고, `종료`는 하위 메뉴에 넣지 않고 메인 메뉴의 `기타` 바로 아래에 둔다. `기타` 안에서도 독서 보조 기능은 `독서 도구`, 일본어 후처리·음원 기능은 `일본어·미디어 도구`로 묶는다.

상위 메뉴에는 `오늘 급여·휴무 / 오늘 리마인더 / 메일 / 날씨 / 추천 / 손자병법 최신 / 일본어 자막·전자책 / Elmedia 재생 / Hue / AI 사용량 / 저장공간 / 기타·종료` 묶음 사이에 구분선을 둔다. `일본어·미디어 도구` 안에서도 자막·낭독 관련 기능과 MP3 관련 기능 사이를 구분한다.

날씨는 별도 구분선 묶음으로 표시하며 맑음은 노랑, 흐림은 주황, 비는 파랑, 조회 실패는 빨강을 사용한다. 회색 비활성 항목이 되지 않도록 클릭하면 날씨를 즉시 새로고침한다.

추천 결과는 `추천 공고:`와 `추천 경진:`처럼 짧은 머리말을 쓰고, 회사·주최자명은 12자, 제목은 22자를 넘으면 `...`로 줄여 메뉴 폭이 지나치게 넓어지지 않게 한다.

`시급 설정`은 제거된 상태를 유지하며 기존 고정 시급값과 급여 계산은 그대로 쓴다. 북마크 최신화도 별도 항목 없이 앱 시작 시 및 6시간마다 자동 실행한다. `🗑️ 저장공간 관리`와 `종료`는 메인 메뉴에서, `현재 설정 확인`은 `기타`에서 접근한다.

Gmail은 로컬 `gog`의 `pulpilisory@gmail.com` 읽기 전용 OAuth를 사용한다. 파일 키링 암호는 macOS Keychain의 `com.shiftalarm.gog-keyring` 항목에서 런타임에 읽으며 설정 파일이나 소스에 평문으로 저장하지 않는다. 새 메일은 전체 본문·첨부가 아니라 발신자·제목·최대 140자 스니펫만 Codex→Claude 폴백에 보내 1~2문장으로 요약하고, AI 실패 시 기존 규칙 기반 요약으로 자동 복귀한다.
최초 연결 시에는 기존 최근 메일을 기준선으로만 저장해 과거 메일 알림을 한꺼번에 보내지 않고, 다음 조회부터 새로 들어온 메일만 AI 요약한다.

**★ 2026-08-08 재설계**: 원래 `🗑️ 휴지통 비우기`가 `osascript`로 Finder에게 직접 휴지통을 비우게 시켰는데, launchd로 뜬 백그라운드 프로세스에서는 AppleEvent 자동화 권한이 제대로 안 붙어서 클릭해도 조용히 아무 반응이 없었다(이 프로젝트에서 반복적으로 겪은 launchd·AppleEvent 문제와 같은 패턴 — 8-1 참조). 게다가 실패했을 때 띄우려던 오류창(`rumps.alert`)이 백그라운드 스레드에서 호출돼 그 자체가 `NSInternalInconsistencyException`으로 크래시했다는 게 로그로 확인됐다 — 즉 "반응 없음"의 정체는 실패 알림 자체의 크래시였다. 자동 삭제를 억지로 고치는 대신, 클릭하면 시스템 설정의 저장 공간 화면(`open x-apple.systempreferences:com.apple.settings.Storage`)을 열어 사용자가 직접 정리하도록 단순화했다. 휴지통 현재 용량 표시(`get_trash_size_str()`, 순수 파이썬으로 `~/.Trash` 크기 계산)는 메뉴 라벨에 그대로 남겨 정보 제공용으로만 쓴다.

---

## 1. 근무표 데이터

- `d_team_schedule_2026.json` — 날짜(`YYYY-MM-DD`) → 근무 코드(`D`/`S`/`G`/`휴`) 매핑. 엑셀 근무표에서 추출. git으로 추적됨(클라우드 자동화 등 다른 환경에서도 오늘 근무를 판단할 수 있어야 해서 저장소에 포함시킴) — `shift_alarm/` 폴더 안, 스크립트와 같은 위치.
- 코드 매핑: `D`→Day, `S`→Swing, `G`→GY(야간), `휴`→휴무.
- 실제 근무 시간 (`SHIFT_WORK_HOURS`): Day 06:00-14:00 / Swing 14:00-22:00 / GY 22:00-06:00(자정 넘어감).
- 근무표 패턴: 휴무 2일 + 근무 6일 반복이 기본이지만, 실제로는 1일/2일/4일짜리 휴무 블록이 섞여있음(연 1일×10회, 2일×35회, 4일×3회) — 로직 짤 때 "휴무는 항상 2일"이라고 가정하면 안 됨.

## 2. 알람(기상) 시간 — `SHIFT_TIMES`
근무 시작 전 깨워주는 알람. macOS `launchd` plist(`~/Library/LaunchAgents/com.shfitalarm.music.plist`)로 등록되며, 울릴 때 `~/Library/Scripts/shift_alarm_run.sh`가 실행된다. 전날의 좋아요 재생 큐가 클래식과 섞이지 않도록 기존 Elmedia 프로세스를 완전히 종료하고 `Playlist.db`의 `playlist_items`/`item_order`만 비운다. 음악 원본은 삭제하지 않는다. 메뉴의 `🎬 Elmedia 지금 바로 재생`과 `⭐ 좋아요 플레이하기`도 같은 방식을 쓴다. 기상 알람에서는 "아침루틴음악재생" 단축어(유튜브 랜덤 음악)를 실행하지 않아 클래식만 재생한다(★ 2026-08-08, 2026-08-10 큐 DB 초기화 강화).

**★ 2026-08-13 Hue 조명 연동:** 알람 스크립트가 음악을 열기 전에 `Command for Philips Hue`가 연결한 Hue Bridge의 `거실1` 방을 켠다. Command 앱 컨테이너의 기존 Bridge appKey는 실행 순간에만 읽고 코드·생성 스크립트·로그·Git에는 저장하지 않는다. 로컬 네트워크나 Command 연결이 실패해도 음악 알람은 계속 실행한다. Mac은 현재 AC 전원에서 시스템 잠자기 `0`(화면만 10분 뒤 꺼짐)이므로 launchd 실행이 가능하다. Apple `shortcuts` CLI는 설치 직후 `Couldn’t communicate with a helper application` 오류가 확인되어 기상 신뢰성을 위해 필수 경로로 사용하지 않고 Hue Bridge 로컬 API를 직접 사용한다.

메뉴바의 `💡 Hue 거실1 켜기/끄기`를 누르면 Bridge에서 현재 방 전원 상태를 읽고 반대로 전환한다. 네트워크 호출은 백그라운드에서 실행하며 결과는 macOS 알림으로 표시한다(★ 2026-08-13).

**★ 2026-08-13 첫 구현 오류 수정:** Hue API v2의 `room`은 방 메타데이터라서 여기에 PUT한 성공 응답만 보고 실제 점등 성공으로 오판했다. `room.services`에서 `rtype=grouped_light`의 실제 제어 ID를 찾은 뒤 그 리소스의 전원 상태를 GET/PUT하도록 메뉴 토글과 기상 알람을 모두 수정했다. 검증도 API 성공 응답뿐 아니라 grouped_light의 최종 `on.on` 상태를 다시 읽어 확인한다.

**★ 2026-08-18 이어서보기 시 거실 조명 자동 켜기:** "이어서보기 할 때 거실 불이 켜지면 좋겠다"는 요청으로, 메뉴의 `📖 이어서 읽기`(이북)와 일본어 EPUB 이어하기를 누르면 `_turn_on_hue_for_reading()`이 백그라운드 스레드에서 거실 조명을 켠다. 토글 대신 `set_hue_room_power(room_name, on=True)`를 새로 만들어 써서, 이미 켜져 있으면 그대로 두고 꺼져 있을 때만 켠다(토글이면 이미 켜진 상태에서 눌러 꺼버리는 사고가 날 수 있음). 방 조회·grouped_light URL 계산 로직은 `toggle_hue_room()`과 공유하도록 `_hue_grouped_light_url()`로 뺐다. 실패해도 책은 이미 열렸으니 조용한 `rumps.notification`으로만 알리고 음성으로 방해하지 않는다.

**★ 2026-08-12 `Nothing to open` 근본 원인 발견·수정**: 2026-08-11에 "폴더째 넘기지 않고 `~/.shift_alarm_playlists/classic.m3u8`(실제 음원만 나열)을 여는 방식이 `Nothing to open` 오류를 막아준다"고 판단해 M3U8 방식으로 바꿨는데, **이 판단 자체가 틀렸다** — 알람이 그 뒤로도 계속 안 울리는 신고가 이어졌다(3번째 재발). 실제 원인: Elmedia는 Mac App Store 샌드박스 빌드라서, `open -a`로 M3U8 파일 하나만 건네면 macOS가 그 M3U8 자체에는 접근 권한을 주지만 **M3U8 안에 적힌 다른 절대경로(진짜 mp3들)에는 권한을 주지 않는다** — Launch Services는 `open` 인자로 직접 넘어온 파일에만 개별 샌드박스 접근 권한을 부여하고, 앱이 나중에 파일을 파싱해서 알아낸 경로는 전혀 모른다. 그래서 Elmedia 입장에서는 재생목록이 통째로 비어 보여 자체적으로 "Nothing to open. Couldn't find any supported files." 대화상자를 띄웠다(직접 재현 확인: `osascript`로 대화상자의 static text를 읽어 문구 그대로 확인함). **수정**: M3U8을 열지 않고, 폴더 안 트랙 절대경로 전부를 `open -a "Elmedia Video Player"`의 인자로 직접 나열한다(`list_audio_tracks()` → `play_folder_in_elmedia()`/`write_alarm_script()`) — 이러면 각 파일이 사용자가 직접 선택한 것으로 취급돼 macOS가 파일마다 개별 접근 권한을 내준다. 실제로 알람 스크립트를 재생성해 수동 실행한 뒤 Elmedia UI에서 곡 제목·재생 경과 시간이 정상 표시되는 것까지 확인함. `write_elmedia_playlist()`로 M3U8 자체는 여전히 만들지만 이제 "사람이 확인할 트랙 목록" 기록용일 뿐, 실제로 여는 데는 쓰지 않는다.

**★ 2026-08-12 같은 세션에서 큐 뒤섞임 방지 강화**: 위 수정 직후 "좋아요 플레이를 틀어놓고 안 끄고 자면 다음날 아침 알람 때 클래식과 좋아요가 랜덤으로 섞여 재생된다"는 지적을 받았다. 원인은 `reset_elmedia_playlist()`가 `killall`(SIGTERM)만 보내고 5초 안에 안 죽으면 그냥 포기하고 다음 단계로 넘어갔다는 것 — 전날 프로세스가 여전히 살아있는 상태에서 새 트랙들을 `open`으로 열면 재생목록이 "교체"가 아니라 "추가"되는 것으로 보여, 좋아요 큐 뒤에 클래식이 덧붙어 섞인다. `reset_elmedia_playlist()`(Python, 메뉴 클릭용)와 `write_alarm_script()`가 생성하는 셸 스크립트(launchd 알람용) 둘 다에 SIGTERM으로 5초 기다려도 안 죽으면 SIGKILL을 한 번 더 보내는 단계를 추가했다. Python 쪽은 그래도 살아있으면 종료 확인 실패를 호출부에 알려 "성공한 것처럼" 조용히 넘어가지 않고 사용자에게 경고 메시지를 보여준다.

**★ 2026-08-12 알람 자가 검증 로그 추가**: launchd 알람은 사람이 그 순간 지켜보는 게 아니라서, 다음 알람이 실제로 잘 울렸는지는 다음에 세션이 열릴 때야 확인할 수 있다("클라우드에서 도는 예약 에이전트로 다음 날 아침에 확인해달라"는 요청이 있었지만, 클라우드 에이전트는 로컬 맥의 launchctl·프로세스·로그에 접근할 수 없어 그 방식은 쓸 수 없었다). 대신 `write_alarm_script()`가 생성하는 셸 스크립트 맨 끝에 자가 검증 단계를 추가했다 — `open` 실행 4초 후 Elmedia가 실행 중인지(`pgrep`), 창 안에 "Nothing to open"이 떠 있는지 아니면 "Elapsed time"(정상 재생 중 표시)이 있는지를 `osascript`로 읽어 `~/.shift_alarm_alarm_verify.jsonl`에 한 줄(`{"timestamp", "status", "track_count"}`, status는 `playing`/`nothing_to_open`/`not_running`/`unclear`) 남긴다. 다음 세션에서 이 파일을 읽으면 그날 알람이 실제로 재생됐는지 바로 알 수 있다.

| 근무 | 알람 시각 |
|---|---|
| Day | 02:55 |
| Swing | 08:30 |
| GY | 16:30 |

메뉴에서 근무별 알람 시간을 바꿀 수 있고(`⚙️ 알람 시간 설정`), 바뀐 값은 `~/.shift_alarm_config.json`의 `shift_times`에 저장되어 다음 실행에도 유지됨.

## 3. 급여 실시간 확인
- 급여명세서 역산 통상시급(`HOURLY_WAGE = 14861`) 기준. GY는 야간수당 50% 가산(`SHIFT_WAGE_MULTIPLIER`).
- 급여는 드롭다운의 오늘 급여 항목에서 확인한다. 메뉴바 타이틀에는 표시하지 않는다.
- **연차 등 근무표와 다르게 수동으로 오늘 근무를 바꾼 경우**, `manual_shift_date`가 오늘로 저장돼 알람과 급여가 그 수동값을 따른다. 이 예외는 오늘 하루만 유효하며 날짜가 바뀌면 삭제되고 근무표 자동 적용으로 복귀한다. 예전처럼 수동 선택 한 번이 `auto_mode=false`로 영구 저장돼 다음 날에도 전날 근무·알람이 남지 않는다. `오늘 근무 다시 불러오기`는 자동 모드까지 다시 켠다.

## 4. 메뉴바 타이틀 구성
`{근무코드+며칠째}-{날씨 한자} {저장공간} {오늘의 리마인더} {Codex%} {Claude%}` 형태로 표시한다(예: `G3-雨 14 🏋️상 📞동찬 94% 61%`). 운동은 `🏋️상`/`🏋️하`, 전화는 `📞엄마`/`📞민준`/`📞동찬`/`📞동주`로 대상을 바로 표시한다. 급여는 제목에 넣지 않는다.
- **AI 사용량 상태창 직접 표기 (★ 2026-08-05 추가, 2026-08-08 간소화)**: 드롭다운을 열지 않아도 바로 보이도록 타이틀 맨 끝에 글자 없이 `{Codex 주간%}%`(연보라), `{Claude 5시간%}%`(오렌지) 순서로 붙인다. 저장공간의 초록·비 오는 날의 파랑과 겹치지 않도록 Codex는 연보라로 구분한다. Codex는 주기 진행일을 계산해 **현재 날짜까지의 누적 권장량**에 도달하면 빨강으로 바뀐다(1일째 14.3%, 2일째 28.6%, 3일째 42.9% …). Claude는 주간 윈도우 90% 이상에서 빨강이다. 값을 아직 못 가져왔으면 해당 숫자를 생략한다. 자세한 데이터 출처는 14번 항목 참조.
- **★ 2026-08-08 Codex 주기 진행일 추가**: 사용률만으로는 7일 주기의 초반인지 후반인지 알 수 없어 `resets_at - window_minutes`로 주기 시작 시각을 구해 현재가 7일 중 몇 일째인지 자동 계산한다. 메뉴바 타이틀은 공간을 아끼기 위해 사용률만 표시하고, 드롭다운에는 `7일 3% (1/7일째)`, 위젯에는 `Codex 3% · 1/7일`로 표시한다.
- 날씨 아이콘(★ 2026-08-05 이모지→한자로 교체): 강수확률 기준 晴(20% 미만) / 曇(20~50%) / 雨(50%+). 임계값은 기존과 동일, Open-Meteo API·아산시 좌표(`LATITUDE=36.78, LONGITUDE=127.00`) 사용. 근무 표기 바로 뒤에 `-`로 이어붙인다(`_update_title()`).
- **근무 며칠째 표기 + 색상 (★ 2026-08-05 추가)**: `_shift_block_day_number()`가 오늘 근무 코드가 며칠째 연속인지(과거는 근무표 원본 기준) 세서 코드 뒤에 붙인다(`G3`, `D1`, `휴2` 등). GY 숫자는 노란색(`NSColor.systemYellowColor`), 휴무 숫자는 빨간색(`systemRedColor`)으로 표시하고 Day/Swing 숫자는 기본색. 비 오는 날(雨)은 파란색(`systemBlueColor`)으로 표시.
- **저장공간 숫자 색상(★ 2026-08-07: 이모지 제거)**: `💾` 이모지 없이 숫자만 표시하고 항상 색을 입힌다 — 평소엔 초록(`systemGreenColor`), `LOW_STORAGE_WARNING_GB`(5GB) 이하일 때만 빨간색.
- **급여·휴무 항목 색상(★ 2026-08-13)**: 콜백 없는 메뉴 항목이 비활성 회색으로 흐려지지 않도록 근무 중 급여는 초록, 다음 근무 예상은 주황, `오늘은 휴무입니다`는 밝은 청록(`systemTealColor`)으로 명시해 가독성을 유지한다.
  - 구현은 `rumps.App.title`(plain 문자열)을 먼저 설정한 뒤 `NSMutableAttributedString` + `setAttributedTitle_()`로 특정 range에만 색을 덮어씌우는 방식이다. rumps의 `title` setter가 내부적으로 `setTitle_()`을 호출해 attributedTitle을 초기화시키므로, **반드시 plain title 설정 → attributedTitle 설정 순서**를 지켜야 한다.
  - **★ 주의(UTF-16 서로게이트 페어)**: `NSRange`는 UTF-16 코드 유닛 기준인데 `💾` 같은 이모지는 서로게이트 페어라 2유닛을 차지하는 반면 Python `len()`은 1글자로 센다. 색상 범위 계산에 Python `len()`을 그대로 쓰면 💾 뒤에 오는 글자의 색이 한 칸씩 밀리는 버그가 생긴다 — `_utf16_len(s)`(`len(s.encode("utf-16-le"))//2`)로 반드시 UTF-16 유닛 길이를 재서 range를 계산한다.
- **★ 2026-07-24 버그 수정**: 오늘의 리마인더 이모지들을 공백 없이(`"".join`) 이어붙이고 있었는데, 휴무일처럼 리마인더가 여러 개 동시에 뜨는 날은 이모지가 다닥다닥 붙어서 찌그러진 것처럼 보였다 — `" ".join`으로 공백을 넣어 고침.
- **★ 2026-08-07 버그 수정(타이틀 통째로 숨겨짐)**: 월초 휴무 시작일처럼 여러 리마인더 조건이 겹치는 날은 리마인더 토큰이 최대 8개까지 동시에 뜰 수 있었다(예: 2026-08-09 실측 8개). 여기에 날씨·저장공간·AI 사용량 토큰까지 더해지면 타이틀 전체 길이가 너무 길어져 macOS가 메뉴바 공간 부족으로 앱 아이콘을 통째로 숨겨버리는 문제가 실사용에서 발생했다. `_update_title()`에서 리마인더 토큰을 **최대 3개**만 보여주고 나머지는 `+N`으로 압축하도록 고쳤다(전체 목록은 드롭다운에서 그대로 확인 가능). 예: `G5-晴 🏋️상 📞엄마 🧹 +5 클69%`.

## 5. 주간/월간 리마인더 (`REMINDERS`)
교대근무자라 요일이 계속 바뀌므로, 요일이 아니라 근무표의 **"휴무 블록"** 을 기준으로 판단한다. 메뉴의 `🔔 리마인더 켜기/끄기`에서 항목별로 개별 on/off 가능 (`~/.shift_alarm_config.json`의 `reminders_enabled`에 저장).

- **`🔔 오늘 리마인더` 세로 목록(★ 2026-08-07 개선, 2026-08-09 Notion 앱 열기, 2026-08-13 세로화)**: `_build_reminder_status_menu_items()`가 리마인더를 한 줄에 이어 붙이지 않고 한 건당 한 줄로 표시해 메뉴가 가로로 과도하게 넓어지지 않게 한다. 각 줄에는 클릭 콜백(16-2의 "🎎 일일 체크리스트" Notion 페이지로 이동)을 달고, `REMINDER_MENU_COLOR_CYCLE`(주황·파랑·보라·초록·빨강·노랑 순환)로 색을 입힌다. `make_open_url_callback()`은 Notion 도메인을 감지하면 `open -a Notion <URL>`로 데스크톱 앱을 명시하므로, 기본 브라우저가 Chrome이어도 Notion 앱에서 열린다. 일반 웹 링크는 기존처럼 기본 브라우저로 연다.

| 항목 | 조건 |
|---|---|
| 🏋️ 상체/하체 운동 하는 날 | 근무·휴무와 무관하게 2026-08-03 **하체**를 기준으로 **격일(2일 간격)**로 반복(★ 2026-08-07: 기존 3일→2일 교대 간격에서 단순화). 상체와 하체를 매회 번갈아 표시하며 운영시간 때문에 알림을 생략하지 않는다 |
| 📞 엄마한테 전화 | 휴무 블록 첫날 |
| ☕ 카페에서 밥먹고 커피마시면서 병법공부하기 | 휴무 블록 첫날마다 표시. 메뉴에서 개별로 끌 수 있고 해당 날짜 Notion 체크리스트에도 기록됨 (★ 2026-08-13 추가) |
| 📞 허민준한테 전화 | 월 1회: 그 달의 **첫 번째** 휴무 블록 시작일 |
| 📞 동찬이형한테 전화 | 근무표와 무관하게 2026-08-03부터 **21일마다 한 번** |
| 📞 손동주한테 전화 | 근무표와 무관하게 2026-08-05부터 **7일마다(주 1회) 한 번** (★ 2026-08-05 추가) |
| 🚿 화장실 잔떼 및 배수 점검 | 근무표와 무관하게 2026-08-13부터 **7일마다(주 1회) 한 번**. 메뉴에서 개별로 끌 수 있고 해당 날짜의 Notion 체크리스트에도 함께 기록됨 (★ 2026-08-13 추가) |
| 💇 머리 깎는 날 | 근무표와 무관하게 2026-08-13부터 **25일마다 한 번**. 메뉴에서 개별로 끌 수 있고 해당 날짜의 Notion 체크리스트에도 함께 기록됨 (★ 2026-08-13 추가) |
| 💬 코딩학원 카톡방에 연락 | 근무표와 무관하게 2026-08-07부터 **7일마다(주 1회) 한 번** (★ 2026-08-07 추가) |
| 📚 에이전틱 코딩 책 읽기 | 근무표와 무관하게 2026-08-08을 시작일로 **3일마다 한 번** (★ 2026-08-08 추가) |
| 🎉 손동주 쉬는 날 | 동주 본인 근무표(내 근무표와 무관, 별도 계산) 기준 — 아래 5-1 참조 (★ 2026-08-05 추가) |
| 🪒 코털 정리하는 날 | 근무표와 무관하게 2026-08-03부터 **4일마다 한 번**(★ 2026-08-07: 7일→14일→4일로 재조정) |
| 💅 손톱발톱 정리하는 날 | 근무표와 무관하게 2026-08-18부터 **11일마다 한 번** (★ 2026-08-07 14일로 추가 → ★ 2026-08-18 실측 주기가 14일보다 짧아 11일로 재조정, 기준일도 2026-08-18로 갱신) |
| 🎧 이어폰 충전하는 날 | 근무표와 무관하게 2026-08-03부터 **4일마다 한 번** |
| 🧹 카톡 정리 | 휴무 블록 마지막날 |
| 🛍️ 아울렛 쇼핑 | 월 1회: 그 달의 **첫 번째** 휴무 블록 시작일 |
| 🚶 2만보 걷는 날 | **★ 2026-08-07 재설계**: 근무·휴무와 무관하게 2026-08-07부터 7일 주기 안 이틀(0·3일째)에 매주 2회. 예전엔 휴무 블록 첫날·마지막날 기준이었는데, 휴무가 뜸한 주엔 아예 안 뜨는 문제가 있어("일주일에 2번은 있어야 하는데 없다") 근무표와 무관한 고정 주기로 바꿈 |
| 🗺️ 월 1회 나들이 추천 | 월 1회: 그 달의 **마지막** 휴무 블록 시작일(아울렛 쇼핑=첫 번째 블록과 겹치지 않게 배정). `NEARBY_PLACES`(아산시 기준 근교 명소 15곳 — 현충사·외암민속마을·신정호·독립기념관·공산성 등)를 `(연,월)` 기준으로 순환 추천해서 매달 다른 곳이 뜸. 2026-07-24 신규 추가 |
| 🥩 소고기 구워먹는 날 | 월 1회: 나들이 추천과 같은 날(그 달의 **마지막** 휴무 블록 시작일). 휴무일에 있었으면 좋겠다는 요청으로 기존 헬퍼 재사용 (★ 2026-08-07 추가) |

당일 해당하는 리마인더는 앱 시작 시 1회 + 매일 자정 넘어갈 때 1회, macOS 알림(`rumps.notification`)으로 뜨고, 메뉴바 드롭다운에도 `🔔 오늘: ...` 항목으로 표시됨.

### 5-1. 🎉 손동주 쉬는 날 계산 (★ 2026-08-05 추가)

손동주 본인의 실제 근무표(사용자의 D조 근무표와는 완전히 별개)를 기준으로 계산한다. 사용자가 전달받은 정보: **주간 2주 → 야간 2주 로테이션**, **5일 근무 + 2일 휴무** 패턴, **2026-08-04이 야간 첫날**.

- `SONDONGJU_SCHEDULE_ANCHOR = 2026-08-04`(야간 블록 1일째), `SONDONGJU_CYCLE_DAYS = 14`.
- 14일 블록 하나가 정확히 "5일 근무 + 2일 휴무"를 두 번 반복한 것과 같다(5+2+5+2=14)이므로, 주/야간 구분과 무관하게 블록 내 6·7일째(0-idx 5,6)와 13·14일째(0-idx 12,13)가 항상 휴무일이 된다 — `SONDONGJU_OFF_DAY_OFFSETS = (5, 6, 12, 13)`.
- 결과적으로 앵커일부터 **7일 간격으로 이틀씩** 휴무가 반복되는 패턴과 동일하다(주/야간 전환 시점과 무관하게 연속). `_is_sondongju_off_day(d)`가 이 계산을 담당.
- 근무표가 바뀌면(동주가 다른 로테이션으로 이동 등) `SONDONGJU_SCHEDULE_ANCHOR`만 그 시점의 "새 야간(또는 기준) 블록 1일째" 날짜로 갱신하면 된다.

## 저장공간 표시·부족 알림 (2026-08-03, ★ 2026-08-07 이모지 제거)

- 메뉴바 제목에 `123`처럼 시스템 볼륨의 실제 가용 공간을 소수점과 단위 없이, 이모지 없이 숫자만 표시한다(색으로 구분 — 4번 항목 참조).
- 드롭다운에는 `💾 저장공간: 123GB 남음`으로 표시한다.
- 5분마다 갱신하며 가용 공간이 **5GB 이하**가 되면 하루 한 번 `휴지통을 비워주세요` macOS 알림을 띄운다.
- 저장공간 경고만으로 휴지통을 자동 삭제하지 않는다. 사용자가 `🗑️ 휴지통 비우기`를 누른 뒤 용량을 즉시 다시 계산한다.
- **★ 2026-08-18 안전한 캐시 자동 정리 추가**: "System Data"가 너무 커진다는 요청에, launchd 백그라운드 항목은 함부로 끄지 않고(필요한 기능이 멈출 수 있음) macOS 자신이 "안전하게 지워도 된다"고 규약한 `~/Library/Caches`만 자동으로 비운다(`clear_user_caches()`) — 이 디렉터리에 뭔가 저장하는 앱은 지워져도 알아서 다시 만들어낼 책임이 Apple 설계 규약상 있다. 가용 공간이 `LOW_STORAGE_WARNING_GB`(5GB) 이하일 때 `_maybe_auto_clear_caches()`가 실행되며, `CACHE_CLEANUP_COOLDOWN_HOURS`(24시간) 안에는 다시 돌지 않는다(마지막 실행 시각은 config에 `last_cache_cleanup_at`으로 저장). 저장공간 메뉴에 `🧹 지금 캐시 정리` 항목을 추가해 쿨다운 없이 수동으로도 바로 실행할 수 있다. 정리 후 확보한 GB·정리된 개수·(권한 문제 등으로) 건너뛴 개수·남은 용량을 알림으로 표시한다.

## 6. 헬스장 운영시간 (`is_gym_open`, `_gym_time_ok`)
헬스장은 평일 24시간, 토·일요일 06:00~17:00 운영이라는 정보와 판정 함수는 보존한다. 다만 2026-08-03부터 운동 리마인더는 실제 운동 간격을 우선하므로, 근무 종료 시점에 닫혀 있더라도 알림 자체는 생략하지 않는다. 그날 운영시간 안에서 운동 시간을 조정한다.

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
- **2026-08-03 통합**: 단축어와 Shift Alarm은 모두 `run_ebook_reader.sh`를 거쳐 저장소의 `ebook_reader.py` 한 벌만 실행한다. 단축어에서 매번 `pip install`하고 `~/ebook_reader.py`를 덮어쓰는 구형 방식은 사용하지 않는다. 단축어의 셸 스크립트는 아래 두 줄이면 된다.
  ```bash
  READER="/Users/forrestdpark/Desktop/PDG/DailyHelloWorld_/shift_alarm/run_ebook_reader.sh"
  "$READER" "$1"
  ```
- 필수 라이브러리는 매 실행마다 설치하지 않는다. 공용 실행기가 import 여부를 검사하고 실제로 빠진 경우에만 `ebook_reader_requirements.txt`로 설치한다.
- 읽은 세션은 Notion 성공 여부와 관계없이 `~/.ebook_reader/sessions/<시각>_<ID>.json`에 원문 전체·전체 번역·페이지 범위·Notion 상태를 먼저 저장한다.
- Notion의 글자 수와 요청당 블록 수 제한에 맞춰 원문과 번역을 여러 문단·여러 요청으로 나누므로 기존의 원문 1,900자/번역 1,900자 잘림이 없다.
- 동시에 여러 리더를 실행해도 TTS 임시 MP3 이름에 PID를 사용하므로 서로 덮어쓰지 않는다.
- **메뉴바 통합**: 팝업이 아니라 실제 메뉴 항목으로 노출.
  - `📖 이어하기: {책이름 14자로 축약+...} (P.페이지)` — 마지막 읽던 책이 있을 때만 표시, 클릭하면 바로 이어서 실행.
  - `📖 다른 책 선택해서 읽기` — 항상 표시, macOS 파일선택 다이얼로그(pdf/epub)로 새 책 선택.
  - `☁️ 독서 Notion 기록 동기화` — 데이터베이스의 모든 페이지와 하위 블록을 페이지네이션해 `~/.ebook_reader/notion_cache/`에 JSON으로 저장한다. 토큰이 없으면 등록 명령을 안내하고 어떤 데이터도 지우지 않는다.
  - `📘 독서 기록 → 학습판 EPUB` — 원본 PDF/EPUB을 선택하면 같은 책의 로컬 세션과 동기화된 Notion 기록을 모아 원본 옆에 `<책명>_학습판.epub`을 만든다. 세션별 원문·전체 번역·핵심 반복 단어·쉐도잉 문장·과거 기록을 목차로 구성한다.
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
메뉴에서 근무를 수동으로 선택하면 그 날짜의 `manual_shift_date`에 한해서 알람과 급여 계산에 그대로 반영된다. 연차로 쉬는 날은 `휴무`를 선택하면 그날 알람도 꺼지고 급여도 "휴무"로 처리된다. 다음 날짜가 되면 수동 예외를 자동 삭제하고 JSON 근무표로 복귀한다. 장기간 자동 적용 자체를 끄려는 경우에만 별도의 `근무표 자동 적용` 토글을 끈다.

## 10. 🎲 랜덤 추천 사이트 열기 (2026-07-23 추가, 2026-07-27 중복 방지, 2026-08-04 구분선 추가)
메뉴의 `🎲 추천 사이트 열기 (天 폴더 랜덤 3개)`를 누르면 크롬 북마크의 **`天` 폴더 안에서만**(전체 북마크 아님 — 처음엔 전체로 만들었다가 사용자 피드백으로 즉시 天 폴더로 한정함) 무작위로 3개를 뽑아 크롬으로 연다.
- 로직: `RANDOM_BOOKMARK_FOLDER = "天"` 상수로 대상 폴더를 지정. `pick_random_bookmarks(n, folder_name)`이 `~/Library/Application Support/Google/Chrome/Default/Bookmarks`를 읽어 `bookmark_bar`/`other`/`synced` 순서로 재귀 탐색해 그 이름의 폴더를 찾고(같은 이름 폴더가 여럿이면 처음 찾은 것), 그 폴더 안 URL만 모은다. 방문 이력은 `~/.shift_alarm_random_bookmark_history.json`에 저장하며, 아직 열지 않은 URL에서만 무작위 추출한다. 전체 URL을 모두 연 뒤 **다음 클릭부터** 이력을 초기화하고 새 주기를 시작한다. 마지막 묶음은 남은 개수에 따라 1~2개만 열릴 수 있다.
- 북마크에 같은 URL이 여러 번 있어도 추천 후보에서는 하나로 취급한다. 삭제된 URL은 이력에서 자동 제거되고, 새로 추가하거나 주소가 바뀐 URL은 즉시 미방문 후보가 된다. 앱을 재시작해도 이력이 유지된다.
- 다른 폴더로 바꾸고 싶으면 `RANDOM_BOOKMARK_FOLDER` 상수만 바꾸면 됨.
- 뽑힌 3개 URL은 알림(`rumps.notification`)으로도 보여줌.
- 폴더를 못 찾거나 북마크를 못 읽으면(파일 없음/파싱 실패) "오류" 알럿만 띄우고 아무것도 열지 않음.
- **매번 크롬 북마크 파일을 그 자리에서 새로 읽기 때문에, 그 사이 天 폴더에 새로 추가한 북마크도 다음 클릭부터 바로 랜덤 후보에 포함된다** (캐시 없음 — 2026-07-23, 사용자가 "새로 추가한 사이트도 포함되냐" 확인 요청해서 명시).
- **★ 2026-08-04**: 메뉴 항목이 `📘 독서 기록 → 학습판 EPUB`과 `🎥 일본어 자막 추출` 항목들 사이에 구분선 없이 붙어있어서 눈에 잘 안 띈다는 피드백 — 이 항목 앞뒤로 `self.menu.add(None)` 구분선을 추가해서(`build_menu()`) 독립된 항목처럼 보이도록 고쳤다. 기능 자체(콜백·로직)는 변경 없음.

## 10-1. 북마크 자동 최신화 (天 폴더) — krNN. 서브도메인 로테이션 자동 교체 (2026-07-23 추가, 2026-08-01 자동화)

**배경**: topgirl.co(kr41→kr44→kr45), sogirl.so(kr87)처럼 天 폴더 안 일부 사이트는 `krNN.도메인` 형태로 서브도메인 번호가 주기적으로 바뀐다. **루트 도메인(예: `topgirl.co`)엔 DNS 레코드가 아예 없어서**(`nslookup topgirl.co` → "Can't find topgirl.co: No answer", 2026-07-23 확인) 흔한 방법인 "루트 도메인 접속 후 리다이렉트되는 곳 확인"이 안 통한다. 그래서 후보 번호들을 직접 접속 테스트해서 살아있는 걸 찾는 방식으로 구현했다.

별도의 메뉴 항목은 두지 않는다. Shift Alarm을 실행할 때 한 번 확인하고, 이후 **6시간마다 백그라운드에서 자동 확인**한다. 변경이 없으면 조용히 넘어가며, 실제 주소를 바꿨을 때만 macOS 알림을 표시한다.

**자동 확인 시 동작:**
1. `refresh_kr_subdomains()`가 天 폴더 URL 중 `^kr(\d+)\.(.+)$` 패턴(`KR_SUBDOMAIN_RE`)에 맞는 것만 도메인별로 그룹화하고, 그 안에 이미 알고 있는 번호들(예: topgirl.co → {44})을 모은다.
2. `_detect_current_kr_subdomain()`: 알고 있는 번호들을 큰 순서로 테스트해서(`ThreadPoolExecutor`, 병렬) 살아있는 것 중 최댓값을 채택. **알고 있는 번호가 전부 죽어있으면** 최댓값+1부터 +30번까지 새로 탐색(신규 로테이션 대응).
3. `_resolve_kr_number()`(舊 `_host_alive()`): HEAD 요청 후 **HTTP 응답이 왔으면**(200이든 403/503이든) 살아있는 것으로 판단, **DNS 실패/연결 거부/타임아웃일 때만** 죽은 것으로 판단. ★ 처음엔 `status < 400`만 살아있음으로 쳤다가, sogirl.so가 Cloudflare 봇 차단으로 403을 반환하는 걸 확인해서(정상 사이트인데 오탐 처리될 뻔함) HTTPError도 "살아있음"으로 완화했다 — 진짜 로테이션이 끝난 옛 서브도메인(예: kr42.topgirl.co)은 아예 연결 자체가 안 되는 것으로 확인됨(HTTP 에러조차 안 뜸), 이 차이로 구분한다.
   - ★★ 2026-08-04 버그 수정: 로테이션된 옛 서브도메인이 완전히 죽지 않고 **301로 새 번호로 리다이렉트만 하며 계속 응답하는 케이스**(kr44.topgirl.co → 301 → kr45.topgirl.co)가 있었는데, 옛 로직은 "응답만 오면 그 번호 그대로 살아있음"으로 판단해서 리다이렉트를 무시하고 계속 kr44를 최신으로 오판했다 — 6시간마다 자동 확인이 돌아도 영원히 갱신이 안 되는 잠복 버그였다. `_resolve_kr_number()`는 `urlopen()`이 반환한 최종 URL(`resp.geturl()`, HTTPError는 `e.geturl()`)의 호스트명에서 kr번호를 다시 파싱해서 **리다이렉트 최종 도착지의 번호를 반환**하도록 고쳤다(최종 호스트가 kr패턴이 아니면 원래 번호로 폴백). 이 사례로 天 폴더 안 63개 북마크가 kr44→kr45로 한 번에 갱신됨.
4. 바뀔 게 있으면(도메인별 최신 번호와 다른 URL이 있으면) 크롬이 켜져있는지 확인 → 켜져있으면 종료 → 백업(`Bookmarks.bak`) → 파일 갱신 → 크롬 재실행. (북마크관리 프로젝트의 "크롬 켜진 채로 파일 쓰면 덮어써짐" 문제와 동일한 이유로 동일한 해법 적용.)
5. 실제로 주소가 바뀐 경우에만 `rumps.notification`으로 몇 개 바꿨는지 알려준다. 특정 도메인의 현재 살아있는 번호를 못 찾으면(예: 사이트 자체가 완전히 다운) 그 도메인은 `failed_domains`로 기록하고 나머지는 정상 처리한다. 변경 없음과 일시적 탐색 실패는 메뉴를 방해하지 않도록 로그에만 남긴다.
6. 네트워크 확인은 `threading.Thread`에서 실행하므로 확인 중에도 메뉴바 자체가 멈추지 않는다. 이전 확인이 아직 끝나지 않았다면 다음 예약 실행은 중복으로 시작하지 않는다.
7. topgirl.co/sogirl.so뿐 아니라 **`krNN.도메인` 패턴에 맞는 天 폴더 안 모든 사이트**에 자동으로 적용된다(도메인 이름을 코드에 하드코딩하지 않음) — 새로운 사이트가 같은 패턴으로 추가돼도 별도 수정 없이 동작.

**주의**: 실제 변경이 발견되면 북마크 파일이 다시 덮어써지는 것을 막기 위해 Chrome을 잠시 종료하고, `Bookmarks.bak` 백업 후 주소를 수정한 다음 Chrome을 다시 연다.

## 11. 🎥 일본어 자막 추출 연동 (2026-07-23 추가, 2026-07-28 버튼 3개로 분리)

일본어 영상 파이프라인은 메뉴에 버튼 3개로 노출된다 — 운동용 영상 추출과 자막·노션·EPUB 생성을 항상 같이 돌리면 너무 오래 걸려서, 각각 단독으로도 실행할 수 있게 나눴다(자세한 파이프라인 내용·필수 키체인 등록은 `일본어자막추출/README.md` 참조).

- `🎥 일본어 자막 추출 - 연달아 (폴더 선택)` — 기존과 동일, 운동용 영상 → 자막·번역·Notion·EPUB을 한 iTerm 세션에서 순서대로 전부 실행. `JP_SUBTITLE_SCRIPT`(`../일본어자막추출/whisper_series_stream.sh`)를 실행.
- `🏃 운동용 영상만 추출 (폴더 선택)` — Notion/메모/EPUB 전혀 안 건드리고 운동용 고음 영상(+배경음)만 빠르게 뽑는다. `JP_WORKOUT_VIDEO_SCRIPT`(`extract_high_pitch_video.py`)를 폴더 인자 그대로 넘겨 새 Terminal 창에서 실행 — 이 스크립트가 원래도 폴더를 받아 안의 영상을 전부 순회하므로 별도 셸 반복문이 필요 없다.
- `📝 자막·노션·EPUB만 (폴더 선택)` — 운동용 영상 단계를 건너뛰고 자막·번역·후리가나·Notion·메모앱·EPUB만 실행. `JP_SUBTITLE_STAGE2_SCRIPT`(`../일본어자막추출/subtitle_notion_epub_only.sh`)를 실행 — 목표 분량/여유초 키패드가 필요 없어 폴더 선택만으로 바로 시작한다.
- `📖 EPUB 폴더 → 낭독판 EPUB (문장 강조)` — 같은 EPUB 폴더를 선택하면 일본어 TTS, 문장별 SMIL 동기화, Apple Books 자동 페이지 넘김을 포함한 `<작품명>_낭독판.epub`을 같은 폴더에 저장한다. Apple Books 공식 제약에 맞는 고정 레이아웃 EPUB 3 Media Overlays 방식이다. TTS 중단 후 재실행해도 완성된 페이지 캐시는 재사용한다. **이제 일본어 자막 추출의 기본 후처리에도 자동 포함되며, 이 메뉴는 기존 작품을 수동 재생성할 때 사용한다.**
- `run_jp_subtitle_extraction()` / `run_jp_subtitle_stage2_only()`는 각 스크립트를 `subprocess.Popen`으로 그냥 실행만 하고 바로 리턴한다(fire-and-forget) — 스크립트 자체가 내부에서 새 iTerm 창을 열고 실제 작업을 진행하기 때문에, 여기서 결과를 기다리거나 출력을 파싱할 필요가 없다. `run_jp_workout_extraction_only()`는 `bgm_playlist_batch` 실행과 같은 패턴으로 `.command` 파일을 만들어 `open -a Terminal`로 연다.
- 운동용 영상 관련 두 버튼(연달아·운동용만)에서 뜨는 분량·여유초 숫자 키패드는 `_prompt_jp_workout_settings()` 헬퍼 하나를 공유한다. PyObjC `NSPanel`로 구현되어 있다. 메뉴바 앱은 일반 앱 창이 없어 단순 앱 활성화만으로는 현재 사용 중인 창 뒤에 패널이 남을 수 있으므로, `NSModalPanelWindowLevel`과 `orderFrontRegardless()`를 사용해 항상 화면 맨 앞에서 키·포커스를 받도록 한다. 비활성화 시에도 패널을 숨기지 않는다.
- 목표 분량 확인 뒤 `고음 구간 앞뒤 여유 설정 (초)` 키패드가 한 번 더 열린다. 최초 기본값은 목표 30분·여유 1초이고, 확인한 두 값은 `~/.shift_alarm_config.json`에 저장되어 다음 실행의 키패드 기본값으로 그대로 표시된다. 여유는 0 이상의 정수 초를 입력한다. 선택값은 `HIGHLIGHT_PAD` 환경변수와 `--pad` 옵션으로 전달되고 출력 파일명에도 `여유N초`로 기록된다. BGM 결과 파일명에는 실제 음량도 `BGM28퍼센트`처럼 기록된다.
- 노션 토큰/freeimage.host API 키를 키체인에 등록해두지 않으면 새로 뜬 터미널 창에서 "❌ 노션 토큰을 키체인에서 찾을 수 없습니다"로 바로 실패한다 — 최초 1회 `일본어자막추출/README.md`의 키체인 등록 명령 실행 필요(운동용 영상만 추출하는 버튼은 Notion을 안 쓰므로 이 등록 없이도 동작함).

## 11-1. 🎵 플레이리스트 MP4 → 곡별 MP3 자동 분할

메뉴의 `🎵 플레이리스트 MP4 → 곡별 MP3 (폴더 선택)`을 누르면 폴더 선택창이 뜨고, 선택한 폴더 바로 아래의 `.mp4` 파일을 전부 순차 처리한다.

- Shazam 음악 인식은 사용하지 않는다. ffmpeg로 전체 오디오를 한 번 훑어 `-38dB` 이하가 0.35초 이상 이어지는 무음 구간을 찾는다.
- 이전 경계에서 최소 3분이 지난 뒤의 무음만 분절점으로 쓴다. 3~4분 사이에 여러 무음이 있으면 3분 30초에 가장 가까운 지점을 선택한다. 무음 판정은 확실(-38dB/0.35초) → 보통(-34dB/0.22초) → 미세(-30dB/0.12초) 순으로 유동적으로 완화한다. 4분 안에 없으면 같은 기준으로 최대 6분까지 찾고, 6분에도 없으면 6분 지점에서 강제 분절해 40분짜리 조각이 생기지 않게 한다.
- 생성 MP3는 선택 폴더 바로 아래에 `<원본명> 분절1.mp3`, `<원본명> 분절2.mp3` 형식으로 저장한다.
- 분절 경계와 완성 MP3는 `.bgm_split_reports/<고유ID>/.silence_split_state.json`에 한 조각마다 즉시 기록한다. 중단 후 재실행하면 같은 경계의 정상 MP3는 재인코딩하지 않는다. `.bgm_split_reports/source_map.json`에는 `고유ID → 원본 영상명` 대응표를 남긴다.
- 한 MP4의 모든 곡이 MP3로 정상 생성된 경우에만 그 원본을 macOS 휴지통으로 이동한다. 인식 또는 분할이 실패한 MP4는 삭제하지 않고 그대로 보존하며 다음 파일 처리를 계속한다.
- 실제 작업은 일반 Terminal.app 새 창에서 실행해 파일별 진행 상황과 실패 원인을 확인할 수 있다. iTerm 전용 기능은 사용하지 않는다.
- Terminal 창을 닫거나 `Ctrl+C`를 누르면 배치 프로세스가 현재 무음 탐지기와 하위 ffmpeg까지 함께 종료한다.
- 자세한 실행 방식과 재사용 기록은 `일본어자막추출/bgm/README.md`를 따른다.

## 11-2. 🏷️ MP3 Shazam 제목 변경

메뉴의 `🏷️ MP3 Shazam 제목 변경 (폴더 선택)`을 누르면 선택 폴더 바로 아래에서 **파일명에 `분절`이 들어간 MP3만** 한 파일씩 순서대로 처리한다. 이미 곡명이 붙은 일반 MP3는 대상 목록에서 제외한다.

- 각 MP3의 내부 15초 표본 하나만 ShazamIO로 인식한다. 긴 플레이리스트 경계를 찾는 기능이 아니라 이미 분절된 한 곡의 이름만 확인하는 작업이다.
- 인식에 성공하면 즉시 `<아티스트> - <노래제목>.mp3`로 변경한다.
- 같은 이름이 이미 있으면 덮어쓰지 않고 `(2)`, `(3)` 번호를 붙인다.
- 인식 실패 파일은 기존 이름을 유지하고 다음 파일로 넘어간다.
- `.mp3_shazam_rename_state.json`에 파일 지문과 인식 결과를 매 파일 저장한다. 재실행 시 이미 이름을 바꾼 같은 파일은 Shazam 요청 없이 건너뛴다.
- 작업은 일반 Terminal.app에서 실행되며 진행 결과를 파일별로 바로 확인할 수 있다.

## 12. 🌙 앱 실행 중 자동 잠금 방지 (원격 접속용, 2026-08-23 확정)

집 밖에서 mosh/SSH와 원격 UI로 이 맥에 접속할 수 있도록 **Shift Alarm 앱이 실행 중인 동안은 시간표와 관계없이 항상** `caffeinate -d -i -s -u -t 2147483647`을 실행한다. 장기 timeout을 명시해 `-u`가 짧게 해제되지 않게 하고, 시스템·디스플레이 절전과 유휴 상태를 함께 억제한다.

- `get_stay_awake_window(schedule, now, today_override)`: `get_active_shift_window`와 같은 방식(어제 GY가 자정 넘어오는 경우 + 오늘 근무)으로 근무 시작/종료를 찾되, 앞뒤로 `STAY_AWAKE_MARGIN`(1시간)만큼 패딩해서 반환 — `get_active_shift_window`는 "지금 근무 중"일 때만 값을 주지만, 이건 근무 시작 "전"에도(패딩된 시작 시각부터) 이미 창이 열려야 하므로 별도로 만듦.
- `start_caffeinate()`/`stop_caffeinate()`: `~/.shift_alarm_caffeinate.pid`에 PID를 기록해서 관리 — 매분(`_check_stay_awake`, `rumps.Timer(60)`) 지금이 그 창 안인지 확인해서 켜거나 끈다. 앱 시작 시에도 1회 즉시 체크(현재 근무 중에 앱을 재시작해도 바로 켜짐).
- 메뉴바 드롭다운에 `🌙 절전 방지 켜짐 (05:00~15:00, Day)` / `🌙 절전 방지 꺼짐 (근무 전후 1시간 아님)` 형태로 상태 표시(`self.stay_awake_item`).
- 앱 종료(`quit_app`) 시에도 `stop_caffeinate()` 호출 — 앱이 꺼진 채로 caffeinate만 계속 도는 걸 방지.
- `caffeinate -d -i -s -u`는 시스템·디스플레이 절전과 유휴 상태를 모두 막는다. Shift Alarm이 절전 방지를 켠 동안 화면이 계속 켜지고 자동 잠금으로 넘어가지 않으므로, 공용 장소에서는 반드시 수동 토글을 끄거나 앱을 종료해야 한다.
- 기존 근무 전후 시간 창과 수동 `항상 켜기` 토글은 더 이상 실행 조건이 아니다. 앱을 종료하면 `stop_caffeinate()`가 호출되어 macOS의 원래 잠금 정책이 다시 적용된다.

## 13. 자잘한 운영 메모
- 코드/설정 변경 후에는 `launchctl kickstart -k gui/$(id -u)/com.shiftalarm.menubar`로 재시작해야 반영됨 (rumps 앱이라 hot-reload 없음; ★ 2026-07-23부터 LaunchAgent 등록 방식으로 바뀌어 `nohup` 방식은 더 이상 안 씀 — 1번 항목 참조). `SCHEDULE_FILE`/`EBOOK_READER_SCRIPT` 등은 `__file__` 기준 상대경로라 폴더 위치가 바뀌어도 코드 수정 없이 그대로 동작하지만, **plist의 `ProgramArguments` 자체는 절대경로라 폴더/파일을 옮기면 별도로 고쳐야 함**(1번 항목 참조).
- `~/Downloads/shift_alarm.py`에도 항상 최신 사본을 동기화해둠 (사용자가 그쪽에서도 참조하는 습관이 있어서).
- 이 저장소(`DailyHelloWorld`)는 shift_alarm 외에도 손자병법 해석 파이프라인 등 전혀 다른 프로젝트들이 같이 들어있는 개인 모음 저장소라, `git status`에 관련 없는 변경사항(다른 폴더의 M/D/??)이 항상 잔뜩 떠 있다 — shift_alarm.py/ebook_reader.py만 `git add`해서 커밋할 것.
- 여러 세션(로컬 CLI + 웹/모바일 "claude remote-control")이 같은 저장소에 동시에 커밋할 수 있으므로, push 전에 `git fetch && git log HEAD..origin/main --oneline`으로 원격에 새 커밋이 있는지 항상 확인하고, 있으면 merge 후 push할 것.

## 14. 🪙 AI(Codex/Claude) 사용량 표시 (★ 2026-08-05 추가)

Codex와 Claude Code(자기 자신)의 남은 quota/사용량을 메뉴바 드롭다운에서 확인할 수 있다. 별도 파일 `shift_alarm/ai_usage.py`에 데이터 조회 로직을 분리해두고 `shift_alarm.py`가 import한다. aut(github.com/likewoody/aut, Swift 메뉴바 앱)의 데이터 소스 방식을 참고해 구현했다.

드롭다운에 3개 항목이 뜬다(`_check_stay_awake` 토글 항목 바로 아래):
- `🪙 Codex: {윈도우} {사용률}%` — `get_codex_quota()`가 `~/.codex/sessions/**/*.jsonl`을 최신순으로 확인해 가장 최근의 `payload.rate_limits`(primary/secondary)를 읽는다. 네트워크·인증 불필요, 순수 로컬 파일 읽기. **★ 2026-08-08 버그 수정**: Shift Alarm과 Codex가 비슷한 시각에 시작되어 최신 세션 파일에 아직 `token_count`가 없을 때도, 그 직전 세션의 정상 quota를 찾아 표시한다. 예전에는 최신 파일 하나만 읽고 `None`을 12분간 캐시해 메뉴바에서 Codex 토큰만 사라졌다.
- `🪙 Claude: {윈도우} {사용률}%` — `get_claude_live_quota()`가 macOS 키체인의 `Claude Code-credentials`(Claude Code 자신이 이미 저장해둔 OAuth 토큰)로 `GET https://api.anthropic.com/api/oauth/usage`를 호출한다. 비공개 엔드포인트지만 자기 계정 조회에만 쓴다. **토큰 값은 절대 print/log에 노출하지 않는다** — Authorization 헤더로만 사용하고 즉시 스코프에서 제거. **★ 2026-08-08 추가**: `seven_day`(주간) 항목에는 `_claude_seven_day_progress()`가 `resets_at`(다음 초기화 시각)에서 역산한 `(N/7일째)`를 덧붙인다 — 사용률 %만으로는 "이번 주 페이스"를 가늠하기 어렵다는 피드백(예: 3일째에 48%면 여유, 6일째에 48%면 절약 모드 필요).
- `🪙 Claude 로컬: {모델} · 턴 N · 요청 N · 캐시 N%` — `get_claude_local_stats()`가 최근 24시간 이내 수정된 `~/.claude/projects/**/*.jsonl`을 집계해 모델명·유저 턴수·모델 요청수·프롬프트 캐시 적중률을 계산.
- 값을 못 가져오면(로그 없음, API 실패, 키체인 없음 등) **추측하지 않고 "확인 불가"로 표시**한다.
- **★ 2026-08-09 원인 파악·재시도 주기 개선**: `🪙 Claude`가 "확인 불가"로 뜨는 주된 원인은 키체인의 OAuth 액세스 토큰(수 시간짜리, 실측 약 8시간)이 만료됐기 때문 — 이 토큰은 `claude` CLI를 실제로 켜서 쓸 때만 갱신되므로, 밤새 켜지 않으면 아침에 만료 상태로 남는다. 조회가 실패한 상태일 땐 재시도 주기를 12분(`AI_USAGE_NORMAL_INTERVAL`)에서 2분(`AI_USAGE_RETRY_INTERVAL`)으로 당겨서 빠르게 복구를 감지한다.
- **★ 2026-08-14 토큰 자동 갱신(사람이 세션을 안 열어도 복구)**: `_claude_access_token()`이 키체인의 `expiresAt`을 직접 비교해 만료됐거나 5분 이내로 임박했으면, shift_alarm이 자기 자신의 refreshToken을 손대는 대신 **`claude auth status --json`을 서브프로세스로 조용히 실행**해 CLI 자신의 정식 리프레시 흐름을 트리거한 뒤 키체인을 다시 읽는다(리프레시 토큰 직접 로테이션은 여전히 하지 않음 — 위 2026-08-09 항목의 위험 우려 그대로 유지). `claude` 바이너리 경로는 launchd 환경의 최소 PATH를 피해 `shutil.which` 우선 + `/opt/homebrew/bin/claude` 폴백으로 절대경로 사용. 결과적으로 Mac이 켜져 있고 shift_alarm이 12분(또는 재시도 중엔 2분)마다 조회하는 한, 사람이 직접 `claude` 세션을 열지 않아도 "확인 불가"가 자동으로 복구된다.
- **★ 2026-08-05 색상 추가, 2026-08-08 Codex 색상·경고 변경**: `Codex`/`Claude` 두 항목 텍스트 전체에 색을 입힌다 — Codex는 연보라(RGB `0.79, 0.65, 1.0`), Claude(라이브 quota)는 오렌지(`systemOrangeColor`). Codex는 `_quota_window_progress()`로 계산한 현재 일수에 따라 누적 경고선을 `현재 일수 × 100 / 전체 일수`로 정한다(7일 기준 1일째 14.3%, 2일째 28.6% …). Claude는 기존처럼 주간 윈도우 90% 이상에서 빨강이다. `_set_menu_item_color()`가 `NSMenuItem.attributedTitle`을 직접 설정하는 방식이라 rumps `MenuItem.title`이 아니라 `menu_item._menuitem`을 직접 다룬다. `🪙 Claude 로컬` 항목은 색상 없이 기본색 그대로 둔다(quota가 아니라 통계라 임계값 개념이 없음).
- 12분마다 백그라운드 스레드(`_refresh_ai_usage`)로 갱신 + 앱 시작 시 1회.
- Gemini CLI는 이 기기에 설치돼 있지 않아(`~/.gemini` 없음) 데이터 소스에서 제외했다.

## 15. 📱 모바일 접근 (iCloud Drive, ★ 2026-08-05 추가/2026-08-06 Scriptable 홈 화면 위젯 추가)

복잡한 영상 작업 등은 제외하고, 오늘의 근무/리마인더/날씨처럼 기초적인 정보만 아이폰에서도 확인할 수 있게 iCloud Drive를 매개로 연결한다. Notion 동기화나 자체 웹서버(Tailscale 등) 대신, 이미 켜져 있는 iCloud Drive 동기화만 이용하는 가장 단순한 방식을 택했다.

- `shift_alarm.py`가 `_update_title()`이 호출될 때마다(근무/저장공간/리마인더/날씨 등 뭔가 바뀔 때마다) `_write_mobile_status()`로 **세 곳에 동시에** JSON을 갱신 기록한다:
  1. `~/Library/Mobile Documents/com~apple~CloudDocs/ShiftAlarmStatus/status.json` (Finder/Files 앱에서는 "iCloud Drive → ShiftAlarmStatus")
  2. `~/Library/Mobile Documents/iCloud~com~omz-software~Pythonista3/Documents/status.json` (Pythonista 3 앱의 iCloud Documents 폴더)
  3. `~/Library/Mobile Documents/iCloud~dk~simonbs~Scriptable/Documents/status.json` (Scriptable 앱의 iCloud Documents 폴더, ★ 2026-08-06 추가)
- 셋 다 임시 파일에 쓴 뒤 `os.replace()`로 원자적 교체하므로, 동기화 도중 아이폰이 파일을 읽어도 반쪽짜리 JSON을 받을 일이 없다. 한 경로 쓰기가 실패해도(폴더 없음 등) 나머지와 메뉴바 앱 자체 동작에는 영향 없음.
- 파일 내용 예시:
  ```json
  {
    "updated_at": "2026-08-05T19:02:55",
    "date": "2026-08-05",
    "shift": "GY",
    "shift_day_number": 3,
    "weather": "31°C 🌧53%",
    "reminders": ["📞 손동주한테 전화하는 날"],
    "storage_free_gb": 13,
    "earnings_short": "💰 42,300원",
    "codex_percent": 94.0,
    "codex_window_day": 5,
    "codex_window_days": 7,
    "codex_critical": true,
    "claude_percent": 41.0,
    "claude_critical": false,
    "sunzi_title": "9편 구지 15구절 「吾士無余財, 非惡貨也, 無余命, 非惡壽也」",
    "sunzi_url": "https://app.notion.com/p/3ae32a1eae8081c58fe3c047920dca07",
    "job_items": [
      {"category": "career", "label": "커리어", "company": "다믈파워반도체(유)", "title": "AI 업무자동화 엔지니어", "score": 70, "url": "https://www.saramin.co.kr/...", "notion_url": "https://www.notion.so/3b632a1eae8081278fb0e079d8ae26ec"},
      {"category": "parttime", "label": "알바", "company": "글로벌아카데미", "title": "채용 연계형 단기 프로젝트 참여자 모집", "score": 70, "url": "https://www.albamon.com/...", "notion_url": "https://www.notion.so/3b632a1eae8081b683f5e02fd931a5bb"}
    ],
    "contest_items": [
      {"category": "ai", "label": "AI", "organizer": "전국민 AI 경진대회(정부 주관)", "title": "AI 데이터활용 미래역량강화 공모전", "score": 60, "url": "https://aichallenge4all.or.kr/...", "notion_url": "https://www.notion.so/3b632a1eae8081a4995eee02e8dbc56f"},
      {"category": "general", "label": "일반", "organizer": "대전정보문화산업진흥원", "title": "2026년 물류데이터·AI 활용 및 분석 아이디어 공모전", "score": 60, "url": "https://www.contestkorea.com/...", "notion_url": "https://www.notion.so/3b632a1eae80813ea4a4f035c48103d0"}
    ]
  }
  ```
  - **★ 2026-08-08 카테고리 분리**: `job_company`/`job_title`/`job_url`/`job_notion_url`/`job_score` 단일 필드 4종(★ 2026-08-07)이 `job_items` 배열(커리어·알바 각 1건)로, `contest_organizer` 등도 `contest_items` 배열(AI·일반 각 1건)로 바뀌었다 — 취업/알바, AI/일반 특화 경진대회는 성격이 달라 하나로 뭉치면 한쪽이 항상 묻힌다는 지적으로 `get_top_job_analysis(category)`/`get_top_contest_analysis(category)`가 카테고리별 상태 파일(`이직시스템/data/top_job_notion_{career,parttime}.json`, `top_contest_notion_{ai,general}.json`)을 각각 읽어 리스트로 합친다 — 16-1 항목 참조. 아직 분석 전인 카테고리는 배열에서 아예 빠진다.

### 15-1. 아이폰 홈 화면 위젯 — Scriptable (★ 권장, 2026-08-06)

**진짜 홈 화면 위젯(아이콘들 사이에 고정되는 타일)을 원하면 이 방법만 쓴다.** 처음엔 Pythonista로 위젯을 만들었었는데, Pythonista의 위젯 기능은 iOS 14 이전 방식인 Today Widget(NCWidget 확장)이고 **iOS 18부터 애플이 이 확장 방식 자체를 완전히 제거해서 더 이상 동작하지 않는다**(2026-08-06 웹 검색으로 확인 — 위젯 목록에 Pythonista가 아예 안 뜨는 게 정상). Scriptable은 최신 WidgetKit을 지원하는 앱이라 진짜 홈 화면 위젯이 가능하다.

- **`shift_alarm/ShiftAlarmWidget.js`**(git 추적됨) — Scriptable의 `FileManager.iCloud()`로 같은 폴더의 `status.json`을 읽어(iCloud 미다운로드 상태면 `downloadFileFromiCloud()`로 먼저 받음) `ListWidget`으로 그린다. ★ 2026-08-13부터 `sync_scriptable_widget_file()`이 앱 시작과 상태 저장 때 저장소 원본과 iCloud 배포본의 바이트를 비교해 달라질 때만 자동 복사하고 재검증한다. 따라서 Shift Alarm의 위젯 관련 변경은 앱 재시작만으로 Scriptable 파일까지 함께 최신화된다.
- **★ 2026-08-08 iCloud 일시 오류 대응**: Mac이 `status.json`을 원자적으로 교체하는 순간이나 iCloud 다운로드가 지연될 때 Scriptable의 `fileExists`/`readString`이 잠깐 실패할 수 있다. 예전 코드는 파일 부재·다운로드 실패·JSON 읽기 실패를 전부 `status.json을 찾을 수 없습니다`로 표시했다. 이제 iCloud 파일을 정상적으로 읽을 때 `FileManager.local()`의 `ShiftAlarmWidget/status-last-good.json`에도 마지막 성공본을 저장하고, 일시적 실패 시 그 캐시를 표시한다. iCloud와 캐시가 모두 없는 최초 실행에서만 오류 안내가 뜬다.
- **★ 2026-08-13 상태 형식 버전 검사**: Mac은 `widget_schema_version`을 status.json에 기록하고 Scriptable은 현재 버전보다 오래된 iCloud 파일·로컬 캐시를 표시하지 않는다. 예전 `휴 🛌`·구지 15구절 같은 낡은 캐시가 최신 데이터처럼 계속 남는 일을 막는다. 휴무 표시는 이모지 없이 `휴 (N일째)`로 통일했다.
- **★ iCloud 충돌 우회용 V3(2026-08-13)**: 기존 `ShiftAlarmWidget.js`가 iPhone WidgetKit의 충돌 버전으로 고정돼 새 레이아웃 대신 예전 급여 칸을 계속 표시한 사례가 있어, 같은 소스를 `ShiftAlarmWidgetV3.js`에도 자동 배포한다. 이 증상이 발생한 기기는 홈 화면 위젯 편집에서 스크립트를 `ShiftAlarmWidgetV3`로 한 번 다시 선택한다. 이후 `sync_scriptable_widget_file()`이 기존 이름과 V3를 모두 같은 내용으로 유지한다.
- **★ 준실시간 상태 밀어내기(2026-08-13)**: Mac은 상태 변화가 생길 때뿐 아니라 `MOBILE_STATUS_REFRESH_SECONDS=60` 타이머로 세 곳의 `status.json`을 매분 다시 기록한다. Scriptable도 `refreshAfterDate`를 1분 뒤로 요청하며, 위젯의 링크가 없는 영역을 누르면 `ShiftAlarmWidgetV3`가 즉시 실행돼 iCloud 파일을 다시 읽는다. 다만 홈 화면의 자동 실행 시각은 iOS WidgetKit이 배터리·실행 예산에 따라 결정하므로 정확한 1분 자동 갱신은 보장할 수 없다.
- **★ 2026-08-18 iCloud 쓰기가 launchd에서 항상 거부되는 문제 발견·우회**: 재부팅 후 위젯이 갱신을 멈춘 사고 조사 중, launchd LaunchAgent로 뜨는 백그라운드 프로세스는 `~/Library/Mobile Documents/...`(iCloud Drive) 쓰기가 macOS 권한 체계상 **항상** `Operation not permitted`(Errno 1)로 거부된다는 걸 확인했다 — 실행 바이너리(`/opt/anaconda3/bin/python3.11`)에 시스템 설정에서 전체 디스크 접근 권한을 직접 추가하고 LaunchAgent를 완전히 언로드·재로드해도 안 바뀜(실측). 반면 같은 바이너리를 Terminal에서 직접 실행하거나, Launch Services로 뜨는 앱(`open -a`)에서 실행하면 같은 쓰기가 바로 성공한다 — 이미 알려진 8-1번 항목(AppleEvents 우회, StyleEbookTerminal.app)과 근본 원인이 같은 부류의 문제(launchd 백그라운드 프로세스는 macOS가 "진짜 앱"으로 취급하지 않음)다.
  - **우회**: `shift_alarm/iCloudSync.app`(osacompile로 빌드한 작은 컴파일 앱, git 추적됨)에 실제 파일 복사를 위임한다. `_write_mobile_status()`/`sync_scriptable_widget_file()`은 iCloud 대상에 직접 안 쓰고, 로컬(iCloud 아님) 스테이징 파일에 내용을 쓴 뒤 `_sync_files_via_icloud_helper(pairs)`로 (원본, 대상) 경로 쌍을 전달한다.
  - **인자 전달 방식**: `open -a App --args ...`로 인자를 넘기면 osacompile 애플릿의 `on run argv`가 인자를 아예 못 받는 버그가 실측됐다(`argv`가 빈 리스트로 들어옴) — 대신 고정 로컬 경로 `~/.shift_alarm_icloud_sync/manifest.txt`에 줄마다 `원본\t대상` 형식으로 써두고, `open -na iCloudSync.app`(인자 없이)로 띄우면 앱이 그 매니페스트를 읽어 각 줄을 `mkdir -p && cp -f → mv -f`(같은 폴더 내 원자적 교체)로 처리한다. 오류는 `~/.shift_alarm_icloud_sync/error.log`에 남기고, 다음 호출 시 파이썬 쪽이 그 로그를 읽어 출력한 뒤 지운다.
  - **비동기라는 점 주의**: `open -na`는 앱을 띄우기만 하고 바로 반환하므로(대상 앱의 실행 완료를 기다리지 않음), 이 함수 호출은 "복사를 요청했다"는 뜻이지 "복사가 끝났다"는 보장이 아니다. 60초 주기 갱신이라 eventual consistency로 충분하다고 판단해 동기 대기는 넣지 않았다. iCloudSync.app을 재빌드하려면 `osacompile -o iCloudSync.app <script>.applescript` 후 `plutil -insert CFBundleIdentifier -string com.shiftalarm.icloudsync`, `plutil -insert LSUIElement -bool true`, `codesign --force --deep -s -`를 순서대로 실행한다(app_uninstaller의 build_launchpad_app.py와 같은 이유 — Info.plist 수정 후 반드시 재서명 필요).
  - **★ 2026-08-19 Dock 아이콘 깜빡임 버그 수정**: `LSUIElement`를 빼먹은 채 배포해서 매분(`MOBILE_STATUS_REFRESH_SECONDS`) `open -na`로 새로 뜰 때마다 일반 앱처럼 Dock에 아이콘이 잠깐 나타났다 사라지길 반복했다("뭔가 계속 켜졌다 꺼졌다 한다"는 신고로 발견). `Info.plist`에 `LSUIElement=true`를 추가하고 재서명해 백그라운드 전용(Dock 아이콘 없음)으로 고쳤다.
- **★ 휴무 마지막 날 위젯 표기(2026-08-13)**: Mac이 내일 근무표까지 계산해 `shift_is_last_day`를 내려준다. iPhone 위젯에서만 휴무 블록의 마지막 날은 `휴 (2일째/3일째)` 대신 `휴 (마지막날)`로 표시하며 Mac 메뉴바 표기는 바꾸지 않는다.
- **추가 방법**: 홈 화면 길게 눌러 편집 모드 → 왼쪽 위 **"+"** → **Scriptable** 검색 → 크기 선택 → 추가 → 그 위젯을 길게 눌러 **"위젯 편집"** → **Script**를 **`ShiftAlarmWidget`**으로 지정.
- **레이아웃은 `config.widgetFamily`로 위젯 크기에 따라 분기한다(★ 2026-08-06)** — Scriptable은 내용이 위젯 프레임을 넘으면 자동으로 줄여주지 않고 그냥 잘라버리므로, 크기별로 보여줄 내용 자체를 다르게 짰다:
  - **스몰**: 근무·며칠째, 날씨만 (한 줄씩, 최소한만 — 정보 다 넣으면 잘림)
  - **미디엄**: `addStack()` + `layoutHorizontally()`로 좌우 2단
    - 왼쪽: 근무·며칠째, 날씨, 오늘의 리마인더 최대 3개(초과분은 "외 N건"). iPhone에서 확인할 필요가 없는 Mac 저장공간은 표시하지 않는다(★ 2026-08-13).
    - 오른쪽: 🪙 AI 사용량 — 위젯에는 오늘 급여/시급을 표시하지 않는다(★ 2026-08-13). Codex는 현재 진행일까지의 누적 권장량(1일째 14.3%, 2일째 28.6% …)에 도달하면 빨강, Claude는 주간 90% 이상이면 빨강(그 전에는 Codex=연보라/Claude=오렌지)
  - **라지(★ 권장)**: 미디엄 레이아웃 그대로 + 아래에 **⚔️ 손자병법 최신 구절**(`손자병법/README.md`의 "완료된 구절" 표 마지막 줄 — 구절 인용문 「」 포함), **🎯 오늘의 추천 공고**, **🏆 오늘의 추천 경진대회** 추가. 손자병법 제목이나 구절을 탭하면 해당 Notion 페이지(`sunzi_url`)가 열린다(★ 2026-08-08). **★ 2026-08-08 카테고리 2건씩으로 변경**: `job_items`/`contest_items` 배열을 순회해 카테고리(커리어/알바, AI/일반)당 한 줄씩 찍는다 — 항목당 여러 줄(헤딩+본문+링크)을 쓰던 예전 방식으로는 2배로 늘어난 항목이 라지 위젯 프레임을 넘치므로, `[점수] [카테고리] 회사 — 제목` 한 줄로 압축하고 그 줄 자체를 탭하면 바로 Notion AI 분석(`notion_url`)으로 이동하게 했다(원본 공고 링크는 생략 — 분석 페이지 안에 원문 URL이 이미 링크로 들어있다). 두 카테고리 모두 분석 전이면(배열이 비어 있으면) 해당 섹션 전체가 생략된다.
  - 손자병법 완료 표에는 실제 Notion 배포가 끝난 구절을 반드시 한 줄씩 추가한다. 2026-08-13 점검에서 16구절은 완료됐지만 표가 15에서 멈춰 위젯도 15를 표시한 것을 발견해, 16구절 Notion 링크(`3af32a1e...`)를 복구했다.
  - 앱 안에서 재생(▶)으로 직접 실행하면(위젯이 아닐 때) `config.widgetFamily`가 없어서 large로 간주하고 `presentLarge()`로 미리보기를 보여준다.
  - 맨 아래에 갱신시각(스몰 제외)
- Scriptable 앱 안에서 스크립트를 직접 실행하면(위젯이 아닐 때) `presentMedium()`으로 같은 내용을 미리보기로 보여준다(디버깅용).
- status.json에 `earnings_short`(`_earnings_short_text()`)·`codex_percent`/`codex_critical`·`claude_percent`/`claude_critical` 필드가 이때 추가됐다(★ 2026-08-06) — `codex_critical`/`claude_critical`은 메뉴바 타이틀 색상과 같은 `_codex_weekly_critical()`/`_claude_weekly_critical()` 판정을 그대로 재사용해서, 위젯 쪽에서 임계값 로직을 따로 구현할 필요가 없게 했다.

### 15-2. 아이폰에서 텍스트로만 확인 — Pythonista 3

Pythonista 3 앱 안에서 직접 실행해서 텍스트로 볼 때는 여전히 유효하다(위젯이 아니라 앱 내 실행).

- **`shift_alarm/shift_status_pythonista.py`**(git 추적됨) — Pythonista iCloud Documents 폴더(`iCloud~com~omz-software~Pythonista3/Documents/`)에 복사해두면 `console` 모듈로 텍스트를 그대로 출력(근무·며칠째·날씨·저장공간(5GB 이하 빨강)·오늘의 리마인더·갱신시각). 파일 선택기 필요 없음 — Pythonista는 자기 iCloud Documents 폴더 안 파일은 항상 그냥 읽을 수 있어서.
- 아이폰에서 할 일: Pythonista 3 앱 실행 → Documents 목록에서 탭 → 재생(▶).
- `shift_alarm/shift_status_widget.py`(git 추적됨, `appex.set_widget_view()` 사용)도 저장소에 남아있지만 **iOS 18 이상에서는 동작하지 않는다**(위 15-1 참고) — iOS 17 이하 기기가 있다면만 유효.

### 15-3. 아이폰 확인 방법 — iOS 단축어 (수동 설정 1회 필요)

1. 단축어(Shortcuts) 앱 → 새 단축어 생성(또는 `ShiftAlarmStatus` 폴더의 `ShiftAlarm 상태 확인.shortcut`을 Files 앱에서 탭해 가져오기 — 액션 3개(파일 가져오기·사전 열기·Quick Look)가 이미 구성돼 있음, 단 첫 액션은 정식 "파일 가져오기" 액션으로 한 번 교체·재지정 필요했음, 아래 참고).
2. "파일 가져오기" 동작 추가 → iCloud Drive → `ShiftAlarmStatus/status.json` 지정(**이 1회 선택이 보안 스코프 북마크를 만드는 필수 단계 — 건너뛸 수 없음**).
3. "사전 열기(Get Dictionary from Input)" 동작 추가.
4. "사전 값 가져오기"로 `shift`, `shift_day_number`, `weather`, `reminders`, `storage_free_gb` 등 원하는 키를 꺼내 텍스트로 조합하거나, 단순히 "Quick Look로 보기"로 사전 전체를 바로 확인.
5. 위젯으로 보고 싶으면 홈 화면에 단축어 위젯을 추가.
- **미리 만들어둔 `.shortcut` 파일의 한계**: Claude가 macOS `shortcuts sign`으로 미리 서명해 만든 파일은 액션 3개 구조까지는 정상 인식되지만(맥 단축어 앱에서 직접 열어 검증함), 첫 "파일 가져오기" 액션에 정상적인 파일 선택기 연결까지는 자동으로 못 채워 넣는다(탭하면 텍스트 입력만 뜨는 자리표시자 상태). 이 액션을 지우고 앱의 액션 라이브러리에서 정식 "파일 가져오기"를 새로 추가해서 교체해야 한다.

Mac이 잠들어 있거나 앱이 꺼져 있으면 파일이 갱신되지 않으므로, `updated_at` 값으로 최신 정보인지 아이폰에서 확인할 수 있다.

## 16. 💼 이직시스템(job_collector.py) 자동 수집 + 알림 (★ 2026-08-05 추가)

`이직시스템/job_collector.py`(사람인·워크넷 API + 사람인 크롤링, 자세한 내용은 `이직시스템/README.md` 참조)를 shift_alarm이 하루 1번 자동으로 실행하고, 신규 공고가 있으면 macOS 알림으로 알려준다.

### Gmail 전체 새 메일 분석·메일 확인 메뉴 (★ 2026-08-13)

채용·경진대회 메일만 보지 않고 Gmail Inbox의 모든 새 메일을 5분마다 읽기 전용으로 확인한다. `gog` CLI를 `--readonly --gmail-no-send`로 고정 호출하며, 발신자·제목·Gmail snippet을 이용해 `채용 / 경진대회 / 결제·금융 / 보안 / 배송·예약 / 뉴스레터·홍보 / 일반 메일`로 즉시 분류하고 한 줄 요약을 macOS 알림으로 보여준다. 본문이나 OAuth 토큰은 Shift Alarm 설정 파일에 저장하지 않고, 중복 알림 방지용 메일 ID만 최근 200개 보존한다.

메뉴에는 `📧 메일 확인: 최근 N건` 항목이 항상 있으며 연결 후 누르면 Gmail Inbox를 연다. 인증 전에는 `Gmail 1회 연결 필요`로 표시하고, 이때 항목을 누르면 단순히 Gmail 웹을 여는 대신 Terminal에서 `gog --readonly --gmail-no-send auth setup` 안내를 시작한다. 최초 한 번 Google Cloud의 Desktop OAuth client와 Gmail 계정을 읽기 전용으로 연결해야 하며 이후 refresh token은 macOS Keychain에서 관리된다. 이 문구는 미확인 메일 1건이라는 뜻이 아니라 **분석기 최초 연결이 필요하다**는 뜻이다.

- `JOB_COLLECTOR_DIR`/`JOB_COLLECTOR_SCRIPT`: `shift_alarm.py`의 부모 폴더(`DailyHelloWorld_/`) 기준으로 `이직시스템/job_collector.py`를 가리킨다(상대경로, 폴더 이동에도 안전).
- 실행은 `subprocess.run([sys.executable, JOB_COLLECTOR_SCRIPT, "collect"], cwd=JOB_COLLECTOR_DIR, ...)` — shift_alarm과 같은 파이썬 인터프리터(`/opt/anaconda3/bin/python3`)로 돌린다. `job_collector.py`가 표준 라이브러리만 쓰므로 별도 venv 없이도 그대로 동작.
- **마지막 실행 시각을 `~/.shift_alarm_config.json`의 `job_collector_last_run`에 저장하고, 그로부터 24시간(`JOB_COLLECTOR_REFRESH_SECONDS`)이 안 지났으면 건너뛴다.** 앱을 자주 재시작해도(코드 수정 후 매번 kickstart) 사람인 서버에 매번 크롤링 요청을 보내지 않기 위한 안전장치 — 타이머 자체는 24시간 주기지만, 앱이 그보다 자주 재시작되는 경우를 이 저장된 타임스탬프가 실질적으로 막아준다.
- `collect` 명령의 표준출력에서 `신규 (\d+)건 / 기존 갱신 (\d+)건` 패턴을 정규식으로 파싱해서, **신규 공고가 1건이라도 있을 때만** `rumps.notification("💼 이직시스템 새 공고", ...)`을 띄운다. 갱신만 있고 신규가 없으면 알림 없이 조용히 넘어간다(알림 피로 방지).
- `이직시스템/config.json`에 사람인/워크넷 API 키가 없어도 `enable_saramin_crawl: true`면 계속 동작한다(현재 사람인 API 승인 대기 중이라 크롤링만으로 운영 중). **launchd로 뜨는 shift_alarm 프로세스는 사용자의 대화형 셸 환경변수(`export SARAMIN_ACCESS_KEY=...`)를 상속받지 않으므로**, API 키를 실제로 쓰게 하려면 `~/Library/LaunchAgents/com.shiftalarm.menubar.plist`에 `EnvironmentVariables`로 등록하거나 다른 영구 저장 방식이 필요하다 — 아직 미구현, 지금은 크롤링만으로 동작. **DART_API_KEY는 이 문제를 키체인으로 해결했다(★ 2026-08-08)** — `company_profile.py`의 `_dart_api_key()`가 환경변수 우선, 없으면 키체인 `dart_api_key` 항목을 읽는다(`jp_subtitle_notion_token`과 동일 패턴). 사람인/워크넷 키도 필요해지면 같은 방식을 쓰면 된다.
- **메뉴바 드롭다운 표시(★ 2026-08-07: N건 저장됨/상위 공고 목록 제거)**: `score_job()`이 키워드 개수만 세는 단순 점수라 대량 수집·나열은 노이즈만 많다는 사용자 피드백으로, "N건 저장됨"과 "상위 공고 보기" 메뉴를 완전히 없앴다(`get_job_collector_top()`도 호출부가 없어져 코드 자체를 삭제). `collect`는 계속 백그라운드에서 원료 수집용으로만 돌고, 실제로 메뉴에 보이는 건 16-1의 `🎯 오늘의 추천 공고 분석` 한 줄뿐이다. `get_job_collector_summary()`(총건수·최고점수)는 모바일 위젯 JSON에서는 이미 안 쓰지만 함수 자체는 남겨둠(다른 곳에서 값이 필요해지면 재사용).
  - 둘 다 `build_menu()`가 매번 다시 그릴 때(5분마다 자동 새로고침 포함) DB를 다시 읽으므로 최신 상태를 유지한다.

### 16-1. 🎯 오늘의 추천 공고 AI 분석 → Notion 자동 발행 (★ 2026-08-07 추가, 2026-08-08 카테고리 분리)

`collect` 직후 같은 백그라운드 스레드에서 이어서 `이직시스템/job_collector.py analyze-top --category {career,parttime}`을 카테고리마다 한 번씩 실행한다(하루 1번, `collect`와 같은 `job_collector_last_run` 주기를 공유 — 별도 타이머 없음). 적합도 1위 공고의 요구사항·우대사항을 AI(codex→claude 폴백)로 읽어 "① 요약 ② 회사가 실제로 뭘 만들려는지 추론 ③ 연습 프로젝트 추천 ④(★ 2026-08-07) 1인 사업자로 창업한다면의 사업계획서 항목화"를 만들고, `이직시스템/README.md`의 "운영 원칙 — 공고를 학습 커리큘럼으로 쓴다" 문서 자체 원칙을 자동화한 결과를 Notion "🎴 이직시스템" 페이지 밑에 발행한다.

- **★ 2026-08-08 취업/알바 카테고리 분리**: "매일 같은 1위 공고만 추천된다"는 지적(정확히는 "며칠째 피에스티만 나온다")과 별개로, 애초에 취업(사람인·워크넷)과 알바(알바몬·알바천국)는 결이 달라 하나로 뭉치면 한쪽이 항상 묻힌다는 요청으로 `JOB_SOURCE_CATEGORY` 딕셔너리(`job_collector.py`)로 소스를 career/parttime 두 그룹으로 나누고, `analyze_top_job()`이 `--category` 인자로 받은 그룹 안에서만 후보를 고른다. 카테고리마다 독립된 상태 파일(`data/top_job_notion_{career,parttime}.json`)·독립된 Notion 페이지를 갖는다.
- **★ 2026-08-08 "매일 같은 회사만 나옴" 반복 추천 버그 수정**: 점수·마감일로만 정렬하면 동점 1위 공고(예: (주)피에스티)가 마감 전까지 매일 그대로 뽑혀 "갱신이 안 되는 것처럼" 보였다(실제로는 `collect`는 매일 정상 실행 중이었음 — 선택 알고리즘에 반복 방지가 없었을 뿐). `extract_high_pitch_video.py`의 BGM 로테이션(`~/.jp_workout_bgm_history.json`)과 같은 패턴을 적용: `data/top_job_history_{career,parttime}.json`에 "이미 추천한 공고"(`source:source_id`) 목록을 카테고리별로 남겨두고, 다음 실행 때는 그 목록에 없는 후보를 우선 시도한다. 카테고리 후보 풀이 전부 소진되면(모두 이미 추천됨) 히스토리를 초기화하고 다시 1위부터 순환한다. 마감이 지나 후보 풀에서 빠진 공고는 히스토리에서도 자동으로 정리된다.
- 상위 공고가 JS 렌더링·이미지형이라 본문을 못 가져오면(`이직시스템/README.md` 3-2 참고) 자동으로 다음 순위로 내려가며 시도한다(`job_collector.py`의 `analyze_top_job()`, 카테고리당 후보 풀 최대 50개).
- Notion 발행은 `이직시스템/job_collector.py`의 `_notion_publish()`가 직접 Notion REST API를 호출한다(내가/Claude 세션과는 별개 — 백그라운드 프로세스가 독자적으로 쓴다). 토큰은 일본어자막추출과 같은 키체인 항목(`jp_subtitle_notion_token`)을 재사용하며, 사용자가 Notion에서 그 통합을 "🎴 이직시스템" 페이지에 직접 공유해 둬야 한다(API로 자동화 불가능한 수동 1회 설정).
- **페이지 하나만 갱신한다** — 카테고리마다 매일 새 페이지를 만들지 않고, 해당 상태 파일에 저장된 `page_id`가 있으면 기존 자식 블록을 전부 archive한 뒤 새 내용으로 다시 채운다(Notion에 페이지가 쌓이지 않게). 오늘 1위가 어제와 같은 공고면 내용도 그대로 유지된다.
- **메뉴바 표시**: `get_top_job_analysis(category)`가 카테고리별 상태 파일을 읽어 `🎯 [점수] 오늘의 추천 {커리어,알바} 공고: <회사> — <제목>` 항목을 카테고리마다 하나씩 추가한다(★ 2026-08-07: 점수 표기 추가). 클릭하면 `make_open_url_callback()`으로 Notion 페이지가 브라우저에 열린다. 상태 파일이 없으면(첫 실행 전, 토큰 미설정 등) 해당 카테고리 항목만 생략한다.
- Notion 발행이 끝나면 카테고리마다 `rumps.notification(f"🎯 오늘의 추천 {카테고리} 공고", "[점수] <회사> — <제목>", ...)`으로 알려준다.
- AI 폴백 호출이 상위 후보 여러 개를 순서대로 시도할 수 있어 `collect`보다 훨씬 오래 걸릴 수 있으므로, 이 단계만 카테고리마다 별도로 타임아웃 1800초(30분)를 둔다.
- **Notion 페이지 안 URL도 클릭 가능한 링크로(★ 2026-08-07)**: `_markdown_to_notion_blocks()`가 `**볼드**`뿐 아니라 `https?://` 패턴도 감지해서 `rich_text`의 `link` 필드로 만든다 — 이전엔 meta 줄의 공고 원문 URL이 그냥 텍스트로만 보였다.
- **DART_API_KEY 설정 완료(★ 2026-08-08)** — `_rank_candidates_by_analyzability()`가 DART(전자공시) 등록 여부로 후보를 우선 재정렬하는 기능이 이제 실제로 작동한다(16-1 상단 참고, 키는 `company_profile._dart_api_key()`가 키체인 `dart_api_key`에서 읽음).

### 16-1a. 🏆 오늘의 추천 경진대회 AI 분석 → Notion 자동 발행 (★ 2026-08-07 추가, 2026-08-08 카테고리 분리)

공고 분석과 같은 패턴을 공모전/경진대회 도메인에 그대로 적용한다. `_run_job_analysis_top()` 바로 다음, 같은 백그라운드 스레드·같은 하루 1번 주기로 `_run_contest_collector_and_analysis()`가 `이직시스템/contest_collector.py collect`를 한 번 실행한 뒤 `analyze-top --category {ai,general}`을 카테고리마다 실행한다(자세한 크롤링·분석 내용은 `이직시스템/README.md` 3-3 참고).

- **★ 2026-08-08 AI 특화/일반 공모전 카테고리 분리 + 반복 추천 방지**: 16-1과 같은 이유·같은 패턴 — `CONTEST_SOURCE_CATEGORY`(`contest_collector.py`)가 `AI경진대회(정부)` 소스를 `ai`로, 링커리어·콘테스트코리아를 `general`로 나누고, 각각 독립된 상태 파일(`data/top_contest_notion_{ai,general}.json`)·독립된 로테이션 히스토리(`data/top_contest_history_{ai,general}.json`)를 갖는다.
- **메뉴바**: `get_top_contest_analysis(category)`가 카테고리별 상태 파일을 읽어 `🏆 [점수] 오늘의 추천 {AI,일반} 경진대회: <주최> — <제목>` 항목을 공고 분석 항목들 바로 아래에 카테고리마다 하나씩 추가.
- **라지 위젯**: `buildBottomSection()`이 `job_items`/`contest_items` 배열을 순회해 카테고리당 한 줄씩 찍는다(15-1 참고) — 항목이 2배로 늘어 프레임이 빠듯해진 만큼 한 줄로 압축했다.
- 모바일 상태 JSON은 `contest_organizer` 등 단일 필드 대신 `contest_items` 배열(15 참고)을 쓴다.

### 16-2. 🎎 오늘의 리마인더 → Notion 일일 체크리스트 자동 동기화 (★ 2026-08-07 추가)

`_maybe_notify_reminders()`(하루 1번, macOS 알림을 띄우는 그 함수)가 알림과 동시에 오늘의 리마인더 목록을 Notion "🎎 일일 체크리스트" 페이지(`app.notion.com/p/3b532a1eae80803490affd8c9b658711`)에 날짜별 토글 + 체크박스(`to_do` 블록)로 추가한다. 휴대폰 Notion 앱에서 하루 동안 체크해가며 쓸 수 있게 하려는 용도.

- `_sync_reminder_checklist_to_notion()`이 실제 작업을 한다. 네트워크 I/O라 `_maybe_notify_reminders()`(메인 스레드에서 호출됨) 안에서 직접 돌리지 않고 `threading.Thread(daemon=True)`로 분리 — AppKit은 전혀 안 건드리므로 16-3의 크래시 패턴과는 무관하지만, "백그라운드로 뺄 수 있는 I/O는 뺀다"는 이 프로젝트의 기존 원칙을 그대로 따른 것.
- Notion 블록 구조: `{"type": "toggle", "toggle": {"rich_text": [오늘 날짜], "children": [오늘 리마인더 각각을 to_do 블록으로]}}` — 한 번의 `PATCH /v1/blocks/{page_id}/children` 호출로 토글과 그 안의 체크박스들을 동시에 만든다(Notion API가 자식 블록 중첩 생성을 지원).
- 토큰은 일본어자막추출·이직시스템과 같은 키체인 항목(`jp_subtitle_notion_token`)을 재사용한다(`_notion_keychain_token()`). 이 페이지에도 그 통합이 공유돼 있어야 한다.
- **중복 방지**: `~/.shift_alarm_config.json`의 `reminder_notion_synced_date`에 마지막으로 동기화한 날짜를 영구 저장한다. 앱을 하루에 여러 번 재시작해도(코드 수정 후 kickstart 등) 같은 날짜 토글이 중복 생성되지 않는다 — 한 번 만든 뒤엔 사용자가 Notion에서 체크한 상태를 절대 다시 덮어쓰지 않는다.
- 오늘 리마인더가 하나도 없으면(빈 배열) Notion 호출 자체를 생략한다.
- 토큰이 키체인에 없거나 API 호출이 실패해도 조용히 넘어간다(메뉴바 앱 동작에는 영향 없음) — 콘솔에 `⚠️ 리마인더 Notion 동기화 실패` 로그만 남는다.

**★ 2026-08-13 고정형 일일 루틴으로 전환:** 루틴 25개를 날짜마다 복제하지 않는다. `🎎 일일 체크리스트` 상단의 `🌅 오늘의 일일 루틴 — YYYY-MM-DD` 토글 하나만 계속 사용한다. 날짜가 바뀌면 Shift Alarm이 전날 체크 상태를 먼저 읽어 미완료 항목만 macOS 알림으로 보여주고, 같은 체크박스를 모두 해제한 뒤 제목 날짜를 오늘로 바꾼다. 앱이 자정에 꺼져 있었다면 다음 실행 시 수행하며 같은 날짜의 미완료 알림은 한 번만 보낸다. 과거 날짜별 루틴 기록은 삭제하지 않지만 앞으로 날짜 토글에는 조건부 리마인더만 추가한다. 루틴 완료 여부는 메뉴바 타이틀에 표시하지 않는다.

**★ 2026-08-13 `체크안된것` 자동 인덱스:** 페이지 안의 모든 날짜 토글과 현재 고정 루틴을 1분마다 확인해, 체크되지 않은 `to_do`만 `날짜/토글 제목 · 항목명` 링크로 `체크안된것` 토글에 나열한다. 링크는 원본 체크박스 블록을 가리키며 원본을 체크하면 다음 동기화 때 인덱스 항목이 사라진다. 인덱스 자체에는 별도 체크박스를 복제하지 않아 체크 상태의 기준은 항상 원본 하나뿐이다. 고정 루틴은 다음 날 초기화되기 전에 미완료 항목만 전날 날짜 토글에 보존하므로, 그날 놓친 루틴도 나중에 링크를 열어 완료 처리할 수 있다. 이미 내용이 같으면 블록을 다시 쓰지 않아 불필요한 Notion API 호출을 줄인다.

갱신 직전마다 원본 페이지(`3b932a1e-ae80-8021-912b-d160fe6cb629`)의 블록을 API로 다시 읽는다. 일반 문단은 체크 항목, 구분선은 루틴 단계 구분선으로 변환하고 전체 순서의 SHA-256 해시를 저장한다. 같은 날 원본이 바뀌면 이름이 같은 항목의 체크 상태는 유지하면서 고정 루틴만 재구성한다. 원본 조회가 실패하거나 항목이 비어 있으면 오래된 목록으로 덮어쓰지 않고 다음 실행 때 재시도한다.

**★ 2026-08-08 양방향 동기화 추가·실시간화**: 휴대폰 Notion에서 체크한 상태를 1분(`CHECKLIST_SYNC_INTERVAL_SECONDS = 60`)마다 당겨와 메뉴바·위젯 상태 파일에 즉시 반영한다. 이 조회는 AI를 호출하지 않아 토큰 비용이 없고, 분당 몇 번 수준의 Notion 요청은 공식 제한(연결당 평균 초당 3회)보다 충분히 낮다. Scriptable 위젯도 `refreshAfterDate`를 현재 시각+1분으로 요청한다. 단, 실제 홈 화면 갱신 시각은 iOS WidgetKit의 배터리·실행 예산 정책에 따라 늦어질 수 있다.
- `fetch_reminder_checklist_state(token, date_str)`가 페이지 자식 블록 중 `rich_text`가 오늘 날짜와 일치하는 토글을 찾고, 그 토글의 자식(`to_do`) 블록들을 다시 조회해 `{라벨: checked}` 딕셔너리로 반환한다(오늘 토글이 아직 없으면 빈 딕셔너리 — 정상 상황, 예: 오늘 리마인더가 0건인 날).
- `_refresh_checklist_state()`(타이머 콜백, 메인 스레드) → `_fetch_checklist_state_thread()`(백그라운드 스레드에서 네트워크 호출) → 결과를 `self._checklist_state`에 저장 + `~/.shift_alarm_checklist_state.json`에 캐시(오늘 날짜분만 유효, 재시작 직후에도 빈 상태로 안 보이게) → `AppHelper.callAfter()`로 `build_menu()`/`_write_mobile_status()`를 메인 스레드에 재스케줄.
- **메뉴바**: `_build_reminder_status_menu_items()`에 `checklist_state` 인자가 추가돼, 각 리마인더 앞에 `✅`/`⬜`를 붙인다.
- **위젯**: `status.reminders_checked`(`{라벨: checked}`)와 `reminder_notion_url`이 들어간다. `buildLeftColumn()`의 리마인더 목록은 `✅`/`⬜`로 표시되며, `오늘의 리마인더` 제목과 각 항목을 누르면 Notion 일일 체크리스트가 열린다(★ 2026-08-10: 이전에는 URL 필드 자체를 내보내지 않아 탭해도 아무 동작이 없던 버그 수정).
- 앱 시작 시 캐시를 먼저 읽어 즉시 반영(`build_menu()`가 그 값을 참조하므로 반드시 `build_menu()` 호출보다 먼저 초기화해야 함 — 순서를 반대로 했다가 `AttributeError`로 크래시한 적 있음, 초기화 위치는 `__init__` 맨 앞쪽 참고).

### 16-3. ★★ 백그라운드 스레드에서 AppKit 직접 호출 → EXC_BREAKPOINT 크래시 (2026-08-05, 근본 원인 확정)

이 기능을 추가하면서 앱이 재시작 후 20초 안팎으로 죽는 크래시가 실제로 발생했다(`~/Library/Logs/DiagnosticReports/python3.11-*.ips`에 `EXC_BREAKPOINT`/`SIGTRAP`, 스택트레이스는 `NSViewBackingLayer display` → `CA::Transaction::commit` → 백그라운드 pthread 종료 시점).

**근본 원인**: `_init_weather()`(날씨 조회)와 `_fetch_ai_usage()`(Codex/Claude 사용량 조회)가 `threading.Thread`로 띄운 **백그라운드 스레드 안에서** `self._update_title()`(`NSStatusItem.setAttributedTitle_`)과 `_set_menu_item_color()`(`NSMenuItem.setAttributedTitle_`)를 직접 호출하고 있었다. AppKit/Core Animation은 메인 스레드에서만 안전하게 호출할 수 있는데, 이 위반이 지금까지는 "운 좋게" 크래시 없이 넘어갔던 것뿐이었다. 이번에 이직시스템 자동 수집 스레드가 추가되면서 앱 시작 시 동시에 도는 백그라운드 스레드 수가 늘었고(날씨 + AI 사용량 + 이직시스템), 그 동시성이 임계점을 넘겨 실제 크래시로 이어졌다.

**해결**: `PyObjCTools.AppHelper.callAfter()`로 메인 스레드에 작업을 다시 스케줄링하는 패턴을 도입했다.
- `_update_title()`과 `_set_menu_item_color()` 맨 앞에 `threading.current_thread() is not threading.main_thread()` 가드를 넣어, 백그라운드 스레드에서 불리면 `AppHelper.callAfter(...)`로 자기 자신을 메인 스레드에 재스케줄하고 즉시 반환한다.
- `_init_weather()`/`_fetch_ai_usage()`는 이제 네트워크 조회만 백그라운드에서 하고, UI 반영은 각각 `_apply_weather()`/`_apply_ai_usage()`로 분리해서 `AppHelper.callAfter()`로 메인 스레드에 넘긴다.
- 검증: `job_collector_last_run`을 지워서 앱 시작 시 날씨·AI 사용량·이직시스템 스레드가 동시에 뜨는 크래시 재현 조건을 그대로 만든 뒤 재시작 → 55초 이상 안정적으로 생존, 이직시스템 수집도 정상 완료됨을 확인.

## 17. 🔊 알림 음성 낭독 (`notify_spoken`, ★ 2026-08-14 추가)

"예고 없이 뜨는" 알림(추천 공고·경진대회, 오늘의 리마인더, 근무 알람, 새 메일 요약, 동기화 실패 등)은 macOS `say`(한국어 음성 "Yuna")로 함께 읽어준다. `_check_storage`/`play_elmedia_now`처럼 **사람이 방금 직접 클릭해서 생기는 즉각 반응성 알림(Elmedia 재생, Hue on/off, 근무표 자동 모드 토글, 추천 사이트 열기, 북마크 자동 최신화, 일본어 자막·BGM 분할 등 `_now` 계열 "시작됨" 알림)은 제외**하고 `rumps.notification`을 그대로 쓴다 — 매번 소리까지 나면 오히려 방해가 된다는 판단.

- `notify_spoken(title, subtitle, message)`가 `rumps.notification(...)`을 그대로 띄운 뒤, 이모지를 제거한 텍스트를 별도 스레드에서 `subprocess.run(["say", "-v", "Yuna", text])`로 읽는다. 별도 스레드라 메인(UI) 스레드나 호출한 백그라운드 스레드를 막지 않는다.
- 대상 호출부: `_check_storage`(저장공간 부족), `_check_electronics_off`, `apply_today_shift`(근무표 자동 설정 실패), `_maybe_notify_reminders`(오늘의 리마인더), `_notify_incomplete_daily_routine`, `_update_checklist_item_thread`/`_update_daily_routine_thread`(동기화 실패), `_set_shift_internal`(교대근무 알람 설정/해제), `_refresh_gmail_thread`(새 메일), `_run_job_collector_thread`/`_run_job_analysis_top`/`_run_contest_collector_and_analysis`(이직시스템·추천 공고·추천 경진).
- 긴 에러 메시지나 메일 본문 요약이 과하게 길어지는 걸 막기 위해 낭독 텍스트는 400자로 자른다(`SPEAK_MAX_CHARS`). 음성 자체는 `SPEAK_VOICE = "Yuna"`로 고정 — 다른 목소리로 바꾸려면 `say -v '?'`로 설치된 한국어 음성 목록을 확인.

**교훈(다른 백그라운드 스레드 추가 시에도 적용)**: `threading.Thread(target=self.XXX)`로 새 백그라운드 작업을 추가할 때, 그 함수가 끝에서 `self.title =`, `self._update_title()`, `MenuItem.title =`, `setAttributedTitle_` 등 AppKit을 직접 건드리면 반드시 `AppHelper.callAfter()`로 메인 스레드에 넘겨야 한다. `rumps.notification()`과 파일 I/O(`save_config` 등)는 AppKit 뷰 레이어를 직접 안 건드리므로 백그라운드 스레드에서 그대로 호출해도 안전하다(기존 북마크 자동 최신화 스레드도 이 패턴).

## 18. 📧 Gmail 메일 딥링크 (★ 2026-08-14 추가)

"🤖 [분류] 발신자 · 제목" 메뉴 항목과 그 안의 "Gmail에서 열기"를 클릭하면, 인박스 홈이 아니라 **해당 메일 본문으로 바로 이동**한다. `_gmail_message_url(message_id)`가 Gmail API 메시지 id로 `https://mail.google.com/mail/u/0/#all/{id}` 딥링크를 만들고(id 없으면 인박스로 폴백), `make_open_url_callback()`으로 연다. Chrome에서 실제로 열어 본문이 정확히 뜨는 것을 확인했다(id가 Gmail 내부적으로 `#all/{thread-f:...|msg-f:...}` 형태로 리다이렉트됨).

## 19. 📬 채용 메일 → 이직시스템 파이프라인 자동 연동 (★ 2026-08-14 추가)

`gmail search`(목록 조회)는 발신자·제목만 주고 본문/snippet을 주지 않으므로, 지금까지 메뉴에 뜨는 "AI 요약"은 실제 본문이 아니라 발신자+제목 기반 추정이었다. 새 메일 발신자가 사람인(`saramin.co.kr`)이면 `fetch_gmail_message_body(message_id)`(`gog gmail get`)로 전체 HTML 본문을 한 번 더 조회해, `이직시스템/job_collector.py ingest-email`(stdin JSON: sender/subject/body)로 넘긴다.

- `job_collector.py`의 `extract_job_postings_from_email()`이 사람인 뉴스레터의 클릭트래킹 링크(`api-mail.saramin.co.kr/mail-bridge?url=...`)를 복원해 실제 채용공고 URL과 `rec_idx`를 뽑고, AI(`ai_exec.run_ai_exec`)에게 "본문 텍스트 + 후보 링크 순번 목록"을 주고 회사명·제목·마감일을 어느 링크와 짝인지 골라내게 한다(URL 자체를 AI가 베끼게 하면 쿼리스트링을 잘못 옮겨 적을 위험이 있어 인덱스만 고르게 함). rec_idx가 숫자가 아닌 후보(광고 배너 등 깨진 href)는 자동으로 걸러진다.
- 잡코리아 링크는 robots.txt 크롤링 금지(AGENTS.md)로 항상 제외한다. 지금은 사람인만 지원 — 다른 발신자는 `extract_job_postings_from_email()`이 빈 리스트를 반환해 조용히 건너뛴다.
- 추출된 공고는 `source="사람인"`, `source_id=rec_idx`로 `upsert_jobs()`된다 — 기존 사람인 API/크롤링 공고와 **같은 `(source, source_id)` 키로 자연스럽게 중복 제거**되고, `JOB_SOURCE_CATEGORY`에서 이미 `"사람인": "career"`이므로 새 카테고리 등록도 필요 없다. `fetch_job_detail_text()`도 `source_id`(rec_idx)만 있으면 자동으로 크롤링 가능한 구버전 URL로 치환하므로, 이후 파이프라인(점수화·상세 크롤링·AI 분석·Notion 발행)은 기존 사람인 공고와 완전히 동일하게 동작한다.
- **여기서 Notion에 바로 발행하지 않는다.** DB에 반영만 해두면 하루 1번 도는 `_run_job_analysis_top()`(analyze-top --category career)이 점수 1위일 때 자연스럽게 골라 분석·발행한다 — 메일마다 즉시 AI 분석·Notion 발행을 하면 호출 빈도가 너무 잦아지기 때문.
- **검증**: 실제 사람인 뉴스레터 메일(id `19ffedb9d8539413`, 회사 20건 포함)로 별도 테스트 DB에 end-to-end 실행 — mail-bridge 링크 21개 중 숫자 rec_idx 19개 정확히 추출, AI가 19건 전부 회사명·제목·마감일을 실제 메일 내용과 정확히 일치시켜 매칭, `fetch_job_detail_text()`로 그중 1건의 상세 페이지도 정상 크롤링(5356자, `_content_available()` True)됨을 확인.
- `_ingest_job_email_thread(item)`은 `_refresh_gmail_thread`의 새 메일 알림 루프 안에서 발신자가 사람인 도메인일 때만 별도 스레드로 띄운다(AI 호출이 껴 있어 몇십 초 걸릴 수 있어 5분 주기 메일 확인 자체를 막지 않기 위함).

## 20. 🔇 취침 시간대 음성 낭독 음량 축소 (★ 2026-08-16 추가)

**사용자 요청**: "잠든 시간에는 알림 소리를 낮춰서 이야기해달라 — 퇴근 후 3시간 지나면 낮춰라." 알림 자체는 끄지 않는다(자다가도 급한 소식은 들려야 함) — 같은 낭독을 그대로 하되 음량만 낮춘다.

- `_quiet_hours_window(shift)`가 `SHIFT_WORK_HOURS[shift]["end"]`(근무 종료 시각)에 `QUIET_HOURS_AFTER_SHIFT_END`(3시간)를 더한 시각을 조용한 시간대 시작으로, `SHIFT_TIMES[shift]`(다음 기상 알람)를 끝으로 계산한다. 근무별 실측 결과: Day 17:00~02:55, Swing 01:00~08:30, GY 09:00~16:30. 근무 정보가 없으면(휴무 등) 조용한 시간대 자체가 없음 — 항상 평소 음량.
- `_in_time_window(now, start, end)`가 자정을 넘어가는 구간(Day의 17:00~02:55처럼 `start > end`인 경우)도 처리한다.
- `_is_quiet_hours()`가 `load_config()`로 매번 최신 `current_shift`를 읽어 지금이 조용한 시간대인지 판정한다 — 근무를 바꾸면(교대근무 알람 재설정) 바로 반영된다.
- `say` 자체에는 음량 조절 옵션이 없어서, `say -v Yuna -o <임시.aiff>`로 파일에 렌더링한 뒤 `afplay -v <음량>`으로 재생하고 임시 파일을 지운다. **★ 2026-08-17부터는 평소 음량도 이 방식으로 통일**됐다 — 상세는 23번 항목 참고.
- `_speak_text()` 안에서만 판정하므로 `notify_spoken()`을 쓰는 모든 알림(리마인더·근무 알람·새 메일·추천 공고 등, 17번 항목 참고)에 자동으로 적용된다 — 알림 종류별로 따로 설정할 필요 없음.

## 23. 🔊 알림 음성 순차 재생 + 평소 음량 축소 (★ 2026-08-17 추가)

**사용자 피드백**: "알림이 동시에 여러 개 뜨면 하나씩 읽어달라 — 동시에 읽으니까 소리가 이상하게 들린다. 그리고 평소 음량도 지금의 50%로 낮춰달라, 너무 크다."

- **순차 재생**: 예전엔 `_speak_text()`가 호출될 때마다 새 스레드를 그 자리에서 띄워 곧바로 `say`를 실행했다 — 알림이 짧은 간격으로 여러 개 뜨면(예: 새 메일 여러 건이 한 번에 발견됨) 여러 재생이 동시에 겹쳐 소리가 뭉개졌다. 이제는 재생 전담 워커 스레드(`_speech_worker`) 하나가 `_SPEECH_QUEUE`(`queue.Queue`)에서 `(텍스트, 음량)`을 하나씩 꺼내 순서대로 재생한다. `_speak_text()`는 큐에 넣기만 하고 바로 반환하므로 호출한 스레드(메일 확인 루프 등)는 막히지 않는다. 워커는 `_ensure_speech_worker()`가 최초 호출 시 1개만 띄운다(락으로 중복 기동 방지).
- **평소 음량 50% 축소**: `SPEAK_NORMAL_VOLUME = 0.5`를 추가하고, 조용한 시간대가 아닐 때도 이제 `say -o`로 파일 렌더링 후 `afplay -v 0.5`로 재생한다(예전엔 평소엔 `say`를 바로 실행해서 음량 조절이 아예 불가능했다 — 20번 항목의 취침 시간대 축소만 파일 경유였음). 취침 시간대 음량(`SPEAK_QUIET_VOLUME = 0.15`)은 그대로 두되, 재생 경로 자체는 평소/취침 모두 동일한 `_play_speech(text, volume)` 하나로 통일했다.
- 검증: `_speak_text()`를 연달아 3번 호출해도 즉시 반환되고(큐잉), 실제 재생은 겹치지 않고 순서대로 끝나는 것을 실측 확인(3개 순차 재생 시 7초대 — 겹쳤다면 훨씬 짧았을 것).
- **항목 간 무음 텀**: 리마인더처럼 `"\n".join(items)`로 여러 건을 한 번에 `notify_spoken()`에 넘기는 경우(`_maybe_notify_reminders` 등), 예전엔 줄바꿈이 있어도 거의 쉬지 않고 바로 이어 읽어서 항목들이 붙어 들렸다("항목마다 바로바로 나와서 그런데 한 텀 쉬고 이야기했으면"이라는 피드백, ★2026-08-17). `_speak_text()`에서 텍스트의 줄바꿈(`\n`)을 macOS 임베디드 스피치 커맨드 `[[slnc 700]]`(무음 0.7초)로 치환해 `say`에 넘긴다 — 항목 하나하나 사이에 뚜렷한 텀이 생긴다. `afinfo`로 실측: 같은 3문장이 무음 삽입 전 2.8초 → 삽입 후 4.5초로 늘어난 것을 확인.

## 21. 🇯🇵 일본어 EPUB 그냥 열기 (★ 2026-08-17 추가)

기존 8번 항목의 `ebook_reader.py`(TTS 낭독 + 번역 + Notion 기록)와 별개로, 일본어 공부용 EPUB(일본어자막추출 파이프라인이 만드는 낭독판 등)은 **그냥 macOS 기본 EPUB 뷰어(Apple Books)로 열기만** 하면 된다는 요청으로 추가했다. TTS·번역·Notion 기록 없음 — `open` 한 번으로 끝.

- `choose_jp_epub_file()`이 파일 선택 다이얼로그(타입 `epub`만, 기본 위치는 일본어자막추출의 완성 EPUB 폴더 `JP_COMPLETED_EPUB_DIR`)로 한 권을 고른다.
- `open_jp_epub(path)`가 `subprocess.Popen(["open", path])`로 여는 게 전부다. `open`은 Launch Services를 통하는 호출이라 launchd 백그라운드 프로세스에서도 자동화 권한 없이 항상 동작한다(8-1번 항목의 `.command` 런처와 같은 이유).
- 마지막으로 연 파일은 `~/.jp_epub_reader_last.json`에 경로만 저장한다(`EBOOK_LAST_STATE_FILE`과는 완전히 별개 파일 — 페이지/진행률 개념이 없으므로 그냥 "마지막 파일 경로"만 기록).
- **메뉴 위치**: `📖 이어하기` 바로 아래에 `🇯🇵 일본어 EPUB 이어보기: {파일명}`이 마지막으로 연 파일이 있을 때만 뜨고, `기타 → 📚 독서 도구` 안에 `🇯🇵 다른 일본어 EPUB 선택`이 항상 뜬다 — 기존 ebook_reader의 "이어하기/다른 책 선택" 배치를 그대로 따른 것.

## 22. 🎎 일일 체크리스트 Notion 페이지 정리 (★ 2026-08-17 추가)

세 가지를 한 번에 요청받아 같은 동기화 흐름(`_sync_daily_checklist_to_notion`, 하루 1번)에 묶어 넣었다.

- **일주일 넘게 미체크인 항목 자동 체크**: "체크 안 한 지 일주일 넘으면 그냥 알아서 체크되게 해달라"는 요청. `_maintain_checklist_date_toggles(token, today, routine_labels)`가 `YYYY-MM-DD` 형식 제목의 날짜별 토글을 훑어, `(오늘 - 토글 날짜).days > CHECKLIST_STALE_DAYS`(기본 7일)면 남은 미체크 리마인더를 전부 체크 처리한다.
- **날짜 토글에 일일 루틴이 섞여 들어가던 문제 제거**: 예전에는 날짜가 바뀔 때 그날 미완료 일일 루틴 항목을 리마인더와 같은 날짜 토글에 함께 보관했는데(`_sync_daily_checklist_to_notion`의 `date_changed` 분기), "일일 루틴은 하루 지나면 쓸모없으니 리마인더만 남겨달라"는 요청으로 이 보관 로직 자체를 없앴다(전날 미완료 루틴 **알림**은 그대로 유지 — `_notify_incomplete_daily_routine`). 같은 `_maintain_checklist_date_toggles()`가 매일 훑으면서, 혹시 남아있는 루틴 라벨(`DAILY_ROUTINE_SOURCE_PAGE_ID` 원본의 현재 항목 텍스트와 일치하는 to_do)이 날짜 토글 안에 있으면 삭제해 자기 치유(self-healing)한다. 실측: 배포 시점에 이미 섞여 있던 8/14\~8/16 토글에서 루틴 잔재 80개를 제거.
- **🌅 오늘의 일일 루틴 토글을 항상 페이지 맨 아래로**: Notion API에는 기존 블록을 다른 위치로 옮기는 기능이 없어서, `_move_daily_routine_toggle_to_bottom(token)`이 라우틴 토글이 이미 맨 아래가 아니면 통째로 지우고 같은 내용(체크 상태 포함)으로 다시 만든다 — 새 블록은 항상 부모의 끝에 붙으므로 자연히 맨 아래로 온다. `sync_unchecked_checklist_index()`가 이미 쓰던 것과 같은 기법.
- **부수 버그 수정**: `sync_unchecked_checklist_index()`가 직전 실행이 중간에 끊겨 이미 보관(archive)된 블록을 다시 지우려 하면 `400 Bad Request`(`Can't edit block that is archived`)로 전체가 실패하던 문제를 고쳤다 — 이미 archived된 블록의 삭제 실패는 조용히 건너뛴다(결과적으로 이미 지워진 것과 같으므로).

## 24. ✅ 일일 루틴 전부 체크 + 관련 버그 2건 수정 (★ 2026-08-17 추가)

**사용자 요청**: "일일 루틴 체크리스트 하나씩 다 체크하기 귀찮은데 전부체크하기 기능 없나?"

- 루틴 메뉴(`🌅 일일 루틴 체크리스트`)에 아직 안 한 항목이 하나라도 있으면 맨 위에 `✅ 전부 체크` 항목이 나타난다. 누르면 `check_all_daily_routine_now` → `_check_all_daily_routine_thread`가 미체크 항목 라벨을 모아 `update_all_daily_routine_items(token, date_str, labels)`로 한 번에 처리한다 — 토글/자식 목록은 한 번만 조회하고 PATCH만 항목 수만큼 반복하므로, 항목마다 따로 API 왕복하는 것보다 빠르고 Notion 쪽 인덱스 동기화도 마지막에 딱 한 번만 돈다.
- **동시성 버그 발견 및 수정**: 이 기능을 만들다가 로그에 `⚠️ 미완료 체크리스트 인덱스 동기화 실패: HTTP Error 400: Bad Request`가 반복 찍힌 걸 확인했다 — 원인은 리마인더·일일 루틴 항목을 각각 별도 스레드(항목별 락)로 처리하면서 끝날 때마다 `sync_unchecked_checklist_index()`를 부르는데, 짧은 시간에 항목을 여러 개 누르면 이 함수가 동시에 여러 번 실행돼 같은 인덱스 토글 블록(`체크안된것`)을 서로 지웠다 다시 만들며 충돌한 것. 함수 자체를 전역 락(`_UNCHECKED_INDEX_SYNC_LOCK`)으로 감싸 항상 한 번에 하나만 실행되게 고쳤다 — 항목별 락과 무관하게 호출부가 어디든 자동으로 직렬화된다.
- **일본어 EPUB 선택창이 멈춰서 반응 없던 문제 수정**: `choose_jp_epub_file()`/`choose_jp_epub_folder()`/`choose_ebook_file()`가 여는 `choose file`/`choose folder` 패널이 launchd 백그라운드 프로세스(Dock 아이콘 없는 메뉴바 앱)에서 뜨면 포커스를 못 받아 클릭도 안 되고 멈춘 것처럼 보였다(1935번 줄 `NSPanel` 키패드에서 이미 겪었던 것과 같은 원인 — 이 환경에서 배경 프로세스가 띄우는 창은 명시적으로 activate시키지 않으면 다른 앱 창 뒤에서 포커스를 못 받는다). 각 AppleScript 첫 줄에 `activate`를 추가해 osascript 자신을 앞으로 가져오도록 고쳤다.
- **EPUB 파일이 전부 회색으로 선택 불가였던 문제 수정**: activate 수정 이후에도 "폴더 안의 진짜 epub 파일들이 다 회색으로 나온다"는 문제가 남아있었다 — `choose file of type {"epub"}`처럼 확장자로 필터를 걸면, UTI를 등록하지 않은 osascript 프로세스에서는 확장자→UTI 매칭이 제대로 안 돼 대상 파일까지 선택 불가로 표시되는 알려진 AppleScript 문제였다. `choose_jp_epub_file()`과 `choose_ebook_file()` 둘 다 `of type {...}` 필터를 아예 빼서 모든 파일을 선택 가능하게 바꿨다(어차피 기본 위치가 해당 폴더라 실사용에 문제 없음).

## 25. 📧 위젯 메일 요약 + 채용 메일 즉시 분석 + 메뉴 표시 개선 (★ 2026-08-18 추가)

- **위젯에 최근 메일 요약 노출**: 지금까지 메뉴바에만 쌓이던 `gmail_recent_summaries`(최근 AI 요약 메일)를 `status.json`의 `mail_items`로도 내보낸다. `ShiftAlarmWidget.js`의 large 레이아웃 `buildBottomSection()`에 "📧 최근 메일" 섹션을 추가해 손자병법/추천 공고·경진대회 아래에 카테고리·발신자·제목 한 줄로 표시하고, 탭하면 해당 Gmail 메일로 바로 이동한다(★ 표시 개수는 26번 항목에서 1건으로 축소됨).
- **채용 메일 감지 시 즉시 분석**: 예전엔 발신자가 정확히 `saramin.co.kr`일 때만 `ingest-email`을 호출했는데, AI가 분류한 메일 카테고리에 "채용"이 포함되면(발신자 도메인 무관) 폭넓게 트리거하도록 넓혔다 — 실제 추출 지원 여부는 어차피 `job_collector.py`의 `extract_job_postings_from_email()`이 발신자로 다시 검사하므로 안전하다(미지원 발신자면 조용히 "추출된 공고 없음"으로 끝남). `job_collector.py ingest_email()`이 이제 `MAX_SCORE=N` 기계 판독용 줄을 stdout에 추가로 남기고, `_ingest_job_email_thread()`가 이를 파싱해 `JOB_EMAIL_IMMEDIATE_ANALYSIS_MIN_SCORE`(50점, `PARTTIME_RECOMMENDATION_MIN_SCORE`와 동일 기준 재사용) 이상이면 `"[N점] 점수가 높으므로 추천 채용공고 분석 진행하겠습니다"`를 음성으로 안내한 뒤 하루 1번 배치(`_run_job_analysis_top`)를 기다리지 않고 바로 `career` 카테고리 `analyze-top`을 실행한다. 두 흐름이 같은 analyze-top 로직을 쓰도록 `_run_job_analysis_top_for_category(category, cat_label=None)`로 공통 분리했다.
- **메뉴바 메일 요약 가독성 개선**: "요약이 화살표를 눌러야(하위 메뉴를 펼쳐야) 보이고 회색이라 잘 안 보인다"는 피드백으로 상위/하위 항목 배치를 뒤집었다 — 상위(항상 바로 보임)에 `🤖 [카테고리] {요약 60자}`를 놓고, 제목·보낸사람은 하위 항목으로 내렸다.

## 26. 📱 위젯 표시 1건 축소 + parttime 추천이 며칠씩 안 바뀌던 문제 해결 (★ 2026-08-19 추가)

**사용자 요청**: "메일도 한개, 공고도 한개, 경진대회도 한개씩만 보이게 해줘. 그리고 점수 낮아도 매일매일 다른 게 보이게 해줘."

- **위젯 항목을 카테고리 통틀어 1건으로 축소**: 예전엔 `job_items`/`contest_items`가 카테고리(커리어·알바 / AI·일반)별로 각 1건씩 최대 2건 나왔는데, "폰 화면이 좁다"는 지적으로 카테고리 통틀어 점수가 가장 높은 1건만 남기도록 `_write_mobile_status()`를 고쳤다(메뉴바 드롭다운은 화면이 넓어 기존처럼 카테고리별로 계속 보여준다 — 위젯만의 축소). `mail_items`도 `MOBILE_STATUS_MAIL_LIMIT=1`로 축소하고, `gmail_recent_summaries`를 안읽음 우선 → 유용도(`infer_mail_priority`, 채용/경진대회 최우선·계정 인증 후순위) 순으로 정렬해 그중 안읽은 것 1건만 노출한다.
- **근본 원인 발견 — parttime(알바) 추천이 며칠씩 안 바뀌던 이유**: `job_collector.py`의 `_rank_candidates_by_analyzability()`가 parttime 카테고리에 한해 `PARTTIME_RECOMMENDATION_MIN_SCORE`(50점) 미만 후보를 전부 걸러내는 하드컷을 갖고 있었다 — 조건을 만족하는 알바가 하루도 없으면 `analyze_top_job()`이 "오늘은 표시하지 않습니다"만 출력하고 **아무것도 갱신하지 않은 채 그냥 끝났다.** 그 결과 예전에 우연히 50점을 넘겨 발행됐던 결과가 이후 며칠(심하면 몇 주)씩 그대로 메뉴·위젯에 남아 "매일 똑같은 것만 보인다"는 증상으로 나타났다.
- **해결**: 점수 하드컷 자체를 없애고 순위만 매기도록 고쳤다 — 주제 적합성(코딩·AI·온라인 재택 또는 아산 통근권)은 별도의 `_parttime_recommendation_eligibility()` 필터가 이미 걸러주므로, 그 필터를 통과한 후보라면 점수가 아무리 낮아도 오늘의 순환(`_apply_no_repeat_rotation`) 대상에 남는다 — 즉 조건을 만족하는 알바가 있는 한 매일 무언가는 새로 뽑혀 발행된다. 표시 계층(`shift_alarm.py`의 `get_top_job_analysis()`)에도 있던 "parttime 50점 미만이면 다시 숨긴다"는 이중 방어 로직도 같이 제거했다 — 안 그러면 DB에는 발행됐는데 메뉴·위젯에서만 다시 숨겨지는 모순이 생긴다.
- career/경진대회 카테고리는 애초에 이런 점수 하드컷이 없어서(순수 순위·로테이션만 사용) 영향 없음 — parttime 전용 버그였다.

## 27. 🔇 음성 낭독에서 괄호 안 내용 생략 (★ 2026-08-19 추가)

리마인더 라벨 대부분이 `손톱발톱 정리하는 날(11일마다 한 번)`처럼 괄호로 주기·부가 설명을 달고 있는데, `say`로 그대로 읽으면 부자연스럽다는 피드백. `_speak_text()`에서 이모지를 지운 직후 `re.sub(r"[\(（][^\)）]*[\)）]", "", text)`로 괄호(전각 포함) 안 내용을 통째로 제거하고 남은 중복 공백을 정리한다. **화면 표시(메뉴·알림 배너·Notion)에는 원래 텍스트가 그대로 남는다** — `_speak_text()`는 음성 큐에만 관여하고 `rumps.notification`은 원본 텍스트를 그대로 쓰기 때문. `notify_spoken()`을 쓰는 모든 알림(리마인더·추천 공고/경진대회·메일 요약 등)에 공통 적용된다.

## 28. 📧 새 메일 알림 1건으로 축소 + 경진대회 메일도 즉시 분석 (★ 2026-08-19 추가)

**사용자 요청**: "메일 이렇게 많이 띄울 필요 없는 것 같은데, 가장 중요한 메일 하나만 띄우고 채용공고나 경진대회 메일이면 이직시스템으로 분석해서 어떤 회사·경진대회가 고득점인지 설명하는 알람을 읽어줘."

- **알림도, 메뉴 목록도 1건으로 축소**: 예전엔 새 메일이 한 번에 여러 건 몰리면(최대 10건) 각각 따로 `notify_spoken()`을 불러 알림이 연달아 시끄러웠다 — `_refresh_gmail_thread()`가 이제 이번 배치의 새 메일 중 `priority`(1~5, AI 또는 `infer_mail_priority` 판정)가 가장 높은 1건만 소리 내어 알린다. **★ 요청 정정**: "알림을 한 번만 말하라는 게 아니라 메뉴 드롭다운의 메일 항목 자체가 여러 개 뜨는 걸 1개로 줄여달라"는 것이었다 — `GMAIL_SUMMARY_MENU_LIMIT`을 5→1로 낮춰 메뉴바 `📧 메일 확인` 드롭다운에도 `gmail_recent_summaries`(이미 안읽음 우선·priority 순 정렬됨) 맨 앞 1건만 표시한다. 나머지 항목의 DB 반영·분석 트리거는 알림 없이 조용히 그대로 진행하므로(아래 항목) 데이터 자체는 놓치지 않는다.
- **경진대회 메일도 즉시 분석**: 채용 메일은 이미 ingest-email로 이 메일 안의 공고를 직접 추출해 DB에 반영할 수 있지만(14번 항목), 경진대회/공모전은 이메일 본문에서 개별 대회를 추출하는 파서가 없다(링커리어 등 크롤링 전용). 그 대신 카테고리가 "경진대회"인 메일 자체를 "지금 분석해달라"는 신호로 받아들여, `_maybe_trigger_contest_analysis_from_email()`이 음성으로 감지 사실을 안내한 뒤 하루 1번 배치(`_run_contest_collector_and_analysis`, 링커리어 등 재수집+analyze-top)를 즉시 실행한다. 완료되면 기존 "🏆 추천 경진" 알림이 결과(어떤 경진대회가 몇 점으로 1위인지)를 그대로 읽어준다. 여러 경진대회 메일이 한 번에 몰려도 `self._contest_email_trigger_running` 락으로 중복 실행은 막는다.
- 채용 메일 쪽(`_ingest_job_email_thread`)은 18번 항목의 고득점(50점↑) 즉시분석 로직을 그대로 유지 — 이번 변경은 "알림 개수 축소"와 "경진대회도 채용과 동등하게 즉시 분석" 두 가지만 추가했다.

## 29. 🔍 stdout 버퍼링·analyze-top 크래시·iCloudSync 경쟁 상태 진단·수정 (★ 2026-08-19 추가)

**사용자 신고**: "추천 공고가 며칠째 똑같은 회사만 뜨는데 크롤링이 제대로 되고 있는 게 맞아?"

- **근본 원인 1 — stdout 완전 버퍼링**: launchd LaunchAgent로 뜨는 파이썬은 stdout이 tty가 아니라서 완전 버퍼링(수 KB 단위)된다. 평소엔 print() 호출량이 적어 버퍼가 좀처럼 안 차 로그가 몇 시간~며칠씩 안 보이다가 한꺼번에 쏟아졌다(stderr는 원래도 즉시 flush돼 트레이스백은 바로 보였음). 진단이 사실상 불가능한 상태였다 — `com.shiftalarm.menubar.plist`의 `ProgramArguments`에 `-u`(unbuffered) 플래그를 추가해 해결. 플리스트를 고쳤으니 `launchctl bootout` + `bootstrap`으로 재로드해야 반영된다(1번 항목 참고).
- **근본 원인 2 — analyze-top이 인덱스 갱신 단계에서 조용히 죽음**: `-u`로 실제 로그를 보게 된 뒤 수동으로 `analyze-top`을 돌려보니, 공고 분석·Notion 발행(`✅ Notion 페이지 갱신 완료`)까지는 매번 성공하는데 그 다음 "🎴 이직시스템" 최상위 페이지의 "최근 추천 기록" 인덱스를 갱신하는 `record_top_index_entry()` 호출에서 이따금 `TimeoutError`(순수 네트워크 타임아웃)로 스크립트 전체가 죽었다. 이 호출부 3곳(job_collector.py 2곳, contest_collector.py 1곳)이 전부 `except RuntimeError`만 잡고 있어서 raw `TimeoutError`는 못 걸러졌다 — `except Exception`(+ `# noqa: BLE001`, 이미 이 파일의 다른 "베스트 에포트" 지점에서 쓰던 패턴)으로 넓혀 인덱스 갱신 실패가 본 발행 자체를 죽이지 않게 했다. (다행히 이 크래시는 상태 파일 자체는 이미 써진 뒤에 나서 "오늘의 추천"은 실제로 갱신되고 있었다 — 다만 매번 트레이스백과 함께 비정상 종료해 로그가 지저분했고, 더 이른 단계에서 같은 종류의 예외가 나면 상태 파일 갱신 전에 죽어 진짜로 "며칠째 그대로"가 될 수 있었다.)
- **iCloudSync.app 경쟁 상태(★ 26번 항목 이후 발견)**: 고정된 `manifest.txt` 하나를 여러 `open -na` 인스턴스(60초 주기 갱신 + 메일/채용/경진대회 즉시분석 트리거)가 동시에 열면서 서로 임시파일(`status.json.tmp`)을 가로채 `mv: No such file or directory`가 났다. 매 호출마다 고유한 `manifest_<uuid>.txt`를 쓰고, 앱은 그 순간 존재하는 `manifest_*.txt`를 전부 훑어 처리 후 지우도록 바꿔 경쟁을 없앴다(각 `mv`도 `$DST.tmp.$$`로 PID를 붙여 이중 방어). 이 과정에서 실측한 AppleScript 함정: `do shell script`가 반환하는 여러 줄 문자열은 AppleScript 쪽에서 줄바꿈이 **linefeed가 아니라 return(CR)** 으로 들어온다 — `text item delimiters to linefeed`로 나누면 전혀 안 나뉘고 통째로 한 덩어리가 된다(반면 `read POSIX file ... as «class utf8»`로 읽은 매니페스트 "내용"은 파이썬이 그대로 쓴 진짜 linefeed라 정상 분리됨 — 같은 스크립트 안에 두 종류의 줄바꿈이 섞여 있다는 뜻이니 재작업 시 주의).
- 위 세 가지를 전부 고친 뒤 career/parttime 두 카테고리를 수동으로 재실행해 즉시 새로운 추천으로 갱신되는 것을 확인했다(한중에스에스/롯데리아처럼 며칠 묵은 결과가 사라지고 지텔레마/싸이트로닉으로 교체됨).

## 30. 🎯 추천 공고/경진대회도 리마인더처럼 체크리스트화 + 1건 표시 (★ 2026-08-19 추가)

**사용자 요청**: "추천 공고도 항목 하나씩, 경진대회도 항목 하나씩 뜨게 하고, 리마인더처럼 체크하면 그만 보이는 체크리스트로 만들어줘. 내용 보기 위한 링크는 화살표로 열어서 들어가게 해주고."

- **1건으로 축소**: 메뉴바도 위젯(26번 항목)과 같은 기준으로 바뀌었다 — 카테고리(커리어/알바, AI/일반)별 각 1건씩 최대 2건 보여주던 걸 `get_best_job_recommendation()`/`get_best_contest_recommendation()`(신규 공통 함수, 위젯의 `_write_mobile_status()`와 메뉴의 `build_menu()`가 같이 씀)으로 카테고리 통틀어 점수 1위 1건만 보여준다.
- **화살표로 열어야 링크가 보이는 구조**: 예전엔 상위 메뉴 항목 자체를 클릭하면 바로 URL이 열렸는데, "화살표로 열어서 링크 들어가게 해달라"는 요청으로 상위 항목엔 콜백을 아예 안 걸고(클릭해도 아무 일 없음, 화살표/하위 메뉴로만 진입) 하위 항목에 `📝 Notion 분석 보기`(AI 분석 페이지)와 `🔗 원문 공고 보기`(사람인/링커리어 등 원본 링크) 두 개를 따로 둔다.
- **체크리스트(로컬 전용, Notion 동기화는 안 함)**: 하위 메뉴 맨 아래 `✅ 확인함(오늘 그만 보기)`을 누르면 `check_job_reco`/`check_contest_reco`가 `config["job_reco_checked_date"]`/`contest_reco_checked_date`에 오늘 날짜를 저장하고 메뉴를 다시 그린다 — `_is_job_reco_checked()`/`_is_contest_reco_checked()`가 오늘 날짜와 일치하면 그 항목 자체를 메뉴에서 생략한다. 리마인더 체크리스트(`reminders_checked`)와 달리 Notion에는 동기화하지 않는다(로컬 상태만) — 필요해지면 나중에 확장 가능. 날짜가 바뀌면 자동으로 다시 보인다(체크 상태가 그날 하루만 유효).
- **메일이 촉발한 분석 결과 링크**: 28번 항목의 채용/경진대회 즉시분석이 완료되면 `_attach_mail_analysis_url()`이 그 결과를 만든 메일 항목(`gmail_recent_summaries`)에 `analysis_url`을 붙여둔다. 메일 하위 메뉴에 `📊 이직시스템 분석 결과 보기` 항목이 추가로 나타나 그 메일이 실제로 어떤 분석 결과로 이어졌는지 바로 확인할 수 있다.

## 31. 🔤 리마인더 라벨에서 "하는 날" 제거 (★ 2026-08-19 추가)

`코털 정리하는 날`처럼 대부분의 리마인더 라벨 끝에 붙던 "하는 날"이 불필요하다는 피드백으로 `REMINDERS` 딕셔너리와 운동 리마인더 문자열에서 전부 뺐다(예: `코털 정리하는 날` → `코털 정리`, `아울렛 쇼핑하는 날` → `아울렛 쇼핑`, `{부위} 운동 하는 날` → `{부위} 운동`). 화면 표시와 음성 낭독 둘 다 같은 라벨 문자열을 쓰므로 이 변경 하나로 양쪽 다 반영된다. "가는 날"(헬스장)·"걷는 날"(2만보)·"돌리는 날"(빨래)처럼 "하는 날"이 아닌 다른 표현은 요청 범위 밖이라 그대로 뒀다.

## 32. 📬 채용/경진대회 메일 파이프라인을 범용으로 확장 + 점핏 지원 + 요약 표 발행 (★ 2026-08-20 추가)

**사용자 요청**: 점핏(Jumpit) 메일 링크를 주고 "이 안에 어떤 회사들이 추천됐는지 정리해줄 수 있어?" → 확인 후 "점핏도 지원하도록 파서 추가해" → "이직시스템이 받아들이는 게 크롤링만 있는 게 아니잖아, 메일로 오는 다양한 포지션 제안·공고·경진대회 메일도 지금처럼 분석 가능해야지" → "6개 회사에 대해 파이프라인 돌리고 점수 보여줘" → "Notion에 표로 정리해줘" → "마지막 칼럼에 관련 자격증·공부하면 좋은 것도 추가해줘".

- **점핏 전용 빠른 경로**: `job_collector.py`의 `_extract_jumpit_positions()` — 점핏 "오늘의 포지션 제안" 메일(`help@jumpit.co.kr`)은 회사명·공고명·마감일·기술스택이 클릭트래킹 없이 평문 HTML로 반복되는 구조라 AI 호출 없이 정규식만으로 안전하게 추출한다(`<a href=".../position/ID...">` 등장마다 블록을 나누고 그 안의 첫 두 `<td>텍스트</td>`를 회사명/공고명으로 본다).
- **범용 AI 폴백(핵심 요청)**: 사람인·점핏처럼 전용 처리가 없는 발신자는 이제 `_extract_jobs_via_generic_ai()`(job)/`extract_contests_from_email()`(contest)가 처리한다 — 메일의 모든 `<a href>`를 후보로 두고(수신거부·SNS·고객센터 링크만 제외), AI가 본문과 대조해 실제 채용공고/공모전인 링크만 골라 회사명(또는 주최)·제목·마감일을 매칭한다. 사람인 분기와 같은 기법이지만 도메인 제한과 클릭트래킹 복원 로직만 없앤 버전 — **어느 사이트에서 온 메일이든 같은 방식으로 처리된다.** source_id는 URL 해시로 생성하고, source는 `"이메일(기타)"`로 통일해 `JOB_SOURCE_CATEGORY`/`CONTEST_SOURCE_CATEGORY`에 등록했다(career/general).
- **경진대회 메일도 job과 대칭**: `contest_collector.py`에 `ingest_email()`/`extract_contests_from_email()`을 신규 추가했다(예전엔 이메일 수집 기능 자체가 없어 경진대회 메일 감지 시 매번 전체 재크롤링만 돌렸음, 28번 항목). `shift_alarm.py`의 `_maybe_trigger_contest_analysis_from_email()`을 이 새 ingest-email을 쓰도록 재작성 — 이제 "이 메일 안에 실제로 언급된 대회들"만 추출·채점하고, 전체 재크롤링(및 음성 안내)은 점수가 높을 때만(채용 메일과 같은 기준) 돈다.
- **메일별 Notion 요약 표**: `publish_email_job_summary_table()`/`publish_email_contest_summary_table()` — 점수와 무관하게 그 메일에서 나온 공고/대회 전부를 점수 내림차순 표로 Notion에 발행한다. **회사 | 공고 | 마감일 | 점수 | 준비할 점**(공고 쪽만 — `_suggest_job_prep_tips()`가 한 번의 AI 호출로 각 공고에 지원할 때 미리 준비하면 좋을 자격증·심화 학습 주제를 20자 이내로 제안, 실패해도 표 발행 자체는 계속됨) 형식이다. `ingest_email()`이 `TABLE_URL=` 기계 판독용 줄을 출력하고, `shift_alarm.py`의 `_attach_mail_analysis_url()`이 이를 파싱해 그 메일 항목의 메뉴 하위 메뉴에 "📊 이직시스템 분석 결과 보기"로 연결한다(30번 항목).
- **실측 버그**: 메일별 표를 처음엔 상태 파일 하나(`email_job_summary_state.json`)로 관리했는데, 그러면 `_notion_publish()`의 "페이지 하나만 갱신" 방식 특성상 **다른 메일을 처리할 때마다 직전 메일의 표가 통째로 덮어써졌다**(점핏 표가 사람인 표로 지워짐 — 실측). 발신자+제목의 SHA1 해시로 메일마다 별도 상태 파일(`data/email_summaries/<hash>.json`, contest는 `contest_<hash>.json`)을 쓰도록 고쳐서 메일마다 독립된 페이지를 유지한다.
- **회사명 링크(★ 2026-08-20 추가)**: "표의 회사명을 누르면 그 회사 이직시스템 분석을 볼 수 있게 해달라"는 요청 — `_generate_company_profile_url()`이 표에 나오는 회사마다(중복 제거) `analyze_top_job()`과 같은 기업 경영 분석(DART 재무·홈페이지·뉴스·관련 공고를 모아 AI로 작성, `COMPANY_PROFILE_STATE_DIR` 상태 파일 재사용이라 같은 회사 재분석 시 페이지가 중복으로 안 쌓임)을 만들어 회사명 셀에 하이퍼링크로 건다. 회사 하나의 분석이 실패해도(DART 미등록 등) 그 회사만 평문으로 남고 표 발행 자체는 계속된다.
- **스크린샷+비전 분석 폴백(★ 2026-08-20 추가, 이직시스템/README.md에 상세)**: 점핏처럼 JS 렌더링이라 정적 크롤링이 안 되는 공고는 Playwright로 스크린샷을 찍고 `claude` CLI의 Read 도구로 이미지를 직접 읽어 본문을 추출한다(`run_job_analysis()`가 자동 재시도) — "표준 라이브러리만 사용" 원칙의 유일한 예외로, 사용자가 명시적으로 승인했다.

## 33. ☕ 주간(Day) 근무 마지막날 루틴 리마인더 (★ 2026-08-20 추가)

**사용자 요청**: "주간근무 맨 마지막은 점심 먹고 아아 한잔하면서 헬스장 갔다 오후 9시 이후에 잠드는 리마인더 생성해".

- `REMINDERS`에 `day_shift_last_day_routine` 항목을 추가하고, 새 헬퍼 `_is_day_shift_block_end(schedule, d)`로 "오늘이 Day이고 내일은 Day가 아님"을 판정한다(다음 근무가 휴무든 Swing/GY든 상관없이 Day 블록이 끝나는 날이면 뜬다 — 기존 `_is_off_block_start`와 대칭 구조).
- `get_today_reminders()`의 다른 조건들과 같은 자리에 추가해서 메뉴 표시·음성 낭독(`notify_spoken`)·토글 등 기존 리마인더 인프라를 그대로 탄다(별도 배선 불필요).
- 검증: `d_team_schedule_2026.json` 스캔 결과 2026-08-20, 2026-09-13이 Day 블록 마지막날로 잡히고, 실제로 오늘(2026-08-20) `get_today_reminders()` 호출 시 이 리마인더가 포함되는 것을 확인.

## 34. 🛢️ 엔진오일 교체 리마인더 — 5개월 주기 (★ 2026-08-20 추가)

**사용자 요청**: "오늘 엔진오일 갈았는데 오늘부터 오개월주기로 엔진오일 가는날 리마인더생성해".

- `REMINDERS`에 `engine_oil_change` 항목을 추가하고, 새 헬퍼 `_is_engine_oil_change_day(d)`로 판정한다. 기존 주기 리마인더(코털 정리·손톱발톱 정리 등)는 전부 `(d - anchor).days % N일 == 0` 방식인데, 이번엔 "일" 단위가 아니라 "달" 단위 주기라 그대로 못 쓴다 — 연·월을 직접 정수로 환산해 `(year*12+month) 차이 % 5개월 == 0`인지, 그리고 `day`가 기준일(20일)과 같은지 둘 다 확인한다. 기준일이 20일이라 28일이 최소인 2월을 포함해 모든 달에 존재하므로 말일 보정 로직은 필요 없다.
- `get_today_reminders()`의 다른 조건들과 같은 자리에 추가해서 메뉴 표시·음성 낭독·토글 등 기존 인프라를 그대로 탄다.
- 검증: 기준일 2026-08-20에서 뜨고, 2026-09-20(1개월 후)에는 안 뜨고, 다음 발생일 2027-01-20(5개월 후)에 다시 뜨는 것을 직접 확인.

## 35. 📞 동생한테 전화 리마인더 — 월 1회 (★ 2026-08-20 추가)

**사용자 요청**: "한달에 한번 동생한테 전화하는날 리마인더 생성해".

- `REMINDERS`에 `call_sibling` 항목을 추가하고, 기존 `call_heo_minjun`(월 1회 전화)과 완전히 같은 기준 — `_is_first_off_block_start_of_month()`(이번 달의 첫 번째 휴무 블록 시작일) — 을 그대로 재사용했다. 새 헬퍼는 필요 없었다.
- 메뉴바 타이틀 축약 토큰(`get_today_reminder_title_tokens`)에도 `📞동생`을 추가해 다른 통화 리마인더들과 동일하게 표시되게 했다.
- 검증: 2026-09월의 첫 번째 휴무 블록 시작일(2026-09-06)에 `get_today_reminders()`가 이 리마인더를 포함하는 것을 확인.

## 36. ⏰ Day→GY 전환 휴무일 기상 알람 08:00 (★ 2026-08-22 추가)

**사용자 요청**: "shift alarm 에서 근무가 day 에서 gy 로 바뀌는 사이에 휴일에는 알람을 아침 8시로 맞춰주면 좋을거같아".

- 기존엔 `SHIFT_TIMES["휴무"] = None`이라 휴무일은 무조건 `unregister_alarm()`으로 알람이 완전히 해제됐다. 하지만 Day 근무(기상 알람 02:55)를 마치고 며칠 쉰 뒤 GY 근무(저녁 출근)로 넘어가는 구간은 생활 리듬을 낮으로 되돌려야 해서, 이 특정 전환 구간의 휴무일만 아침 8시 알람을 유지하기로 했다.
- 새 헬퍼 `_is_day_to_gy_off_day(schedule, d)`: `d`가 휴무이고, 그 휴무 블록을 앞뒤로 걸어가며 찾은 직전 근무가 Day, 직후 근무가 GY일 때만 True. 새 상수 `DAY_TO_GY_OFF_ALARM_TIME = {"hour": 8, "minute": 0}`.
- `_set_shift_internal(self, shift, notify=True, date=None)`에 `date` 매개변수를 추가해 휴무 판정 시 어느 날짜 기준인지 알 수 있게 했다(기존엔 근무 이름만 받아서 날짜를 몰랐다). 휴무인데 `_is_day_to_gy_off_day`가 True면 `unregister_alarm()` 대신 08:00으로 `register_alarm()`한다. `apply_today_shift()`가 이 `date`를 그대로 전달한다.
- `show_status()`의 "현재: 휴무 (자동, 알람 없음)" 문구도 이 전환 구간이면 "알람 08:00(Day→GY 전환)"으로 바뀌도록 같이 고쳤다(안 고치면 실제로는 알람이 도는데 메뉴에는 "알람 없음"이라고 잘못 표시됐을 것).
- 검증: 2026년 근무표(`d_team_schedule_2026.json`) 전체를 스캔해 Day 블록 직후 휴무 시작일 15건 전부 `_is_day_to_gy_off_day() == True`, GY/Swing 블록 직후 휴무 시작일(각 15건씩)은 전부 `False`인 것을 확인.

## 37. 📊 메일 분석 결과 체크리스트 (★ 2026-08-22 추가, ★ 2026-08-22 전체 항목화로 확장)

**사용자 요청**: "[점핏] 메일 요약 표 링크가 shift alarm 항목에서 보이게해주는게 좋겠어" → 이후 "메일 처리 다끝나면 전부 shift alarm 에 항목화해서 링크로들어가게끔 해줘 내가 확인하면 체크하고 다음부터안뜨게는 할수있게 해주고".

- 메일 요약 목록(`gmail_recent_summaries`)은 `GMAIL_SUMMARY_MENU_LIMIT`(=1)로 "가장 중요한 메일 1건"만 상위 메뉴에 뜨고, 정렬 기준은 안읽음→priority(31번 항목의 `infer_mail_priority` 참고)다. 이직시스템 분석까지 끝난 메일(`analysis_url`이 붙은 메일)이 이미 읽음 처리됐거나 priority가 낮으면 그 1건에 못 들어서, 표까지 다 만들어놓고도 메뉴에서 링크를 볼 방법이 없었다.
- 처음엔 "최신 1건 고정 노출"(`get_latest_mail_analysis_entry`)로 시작했는데, 곧바로 "전부 항목화하고 확인하면 안 뜨게 해달라"는 요청으로 확장 — `get_unchecked_mail_analysis_entries(config, limit=5)`: `analysis_url`이 있고 `mail_analysis_checked_ids`에 없는 항목을 최신순으로 최대 5개 반환.
- `build_menu()`가 이 목록을 순회하며 각각 `📊 메일 분석 결과: {제목}` 하위 메뉴를 만든다 — 자식으로 `📝 분석 결과 보기`(analysis_url 열기)와 `✅ 확인함(다음부터 안 보이기)`(`make_check_mail_analysis_callback`)를 둔다.
- 리마인더·추천공고 체크와 달리 **날짜로 리셋되지 않고 영구적으로** 사라진다 — `mail_analysis_checked_ids`에 id를 追加해 관리(최근 200개 유지). 메일 하나는 반복되는 하루짜리 항목이 아니라 그 자체로 끝이라 매일 다시 보일 이유가 없다는 판단.

## 37-1. 채용/경진대회 메일 자동 파이프라인 타임아웃 버그 + 완료 알림 (★ 2026-08-22 추가)

**증상**: 새 채용 메일이 와도 "📬 채용 메일 파이프라인" 로그 없이 조용히 아무 일도 안 일어났다. 사용자가 "방금도 메일하나왔는데 계속 메일 올때마다 이파이프라인 돌아가게 해줘"라고 요청해서 조사.

- **원인**: `_ingest_job_email_thread`/`_maybe_trigger_contest_analysis_from_email`의 `subprocess.run(..., timeout=200)`이 너무 짧았다. 회사마다 DART/뉴스 조회 + AI 경영분석 + 공고별 준비할 점 생성까지 붙으면서(32번, 38번 항목) 실측 5~8분이 걸리는데 200초(3분 20초)면 항상 타임아웃 났다. 로그에도 `Command [...] timed out after 200 seconds`가 남아 있었다 — 몰랐던 이유는 이 오류가 `print()`로만 남고 알림은 안 떴기 때문.
- **수정**: 하루 1번 도는 `analyze-top`과 같은 1800초로 늘림. 겹쳐 도는 것을 막는 락(`_job_email_trigger_running`)도 job 쪽에 추가(경진대회 쪽엔 이미 있던 패턴 재사용).
- **완료 알림 추가**: "메일 왔다고만 하지 말고 분석 끝나서 shift alarm 항목화 완료했다고 알려달라"는 요청 — 표 발행(analysis_url 부착)이 끝날 때마다 점수와 무관하게 "📊 메일 분석 완료" 음성 알림을 추가했다. 기존 고득점 전용 알림은 "🔍 감지"에서 "💼/🏆 고득점 발견"으로 문구를 구분했다(둘 다 필요 — 하나는 "표가 준비됐다", 하나는 "점수가 높아서 하루짜리 대표 분석까지 돌린다"는 서로 다른 의미).
- 검증: 놓쳤던 점핏 메일을 `gmail_seen_ids`에서 제거해 "새 메일"로 재감지시킨 뒤, 실제로 1800초 타임아웃 안에 완료되고 `analysis_url`이 자동으로 붙는 것을 확인.

## 37-2. Hue "거실1" 알람 연동의 숨은 jq 경로 버그 (★ 2026-08-23 발견·수정)

**사용자 요청**: "알람시작할때 거실1 켜기상태로 만들어주면 좋겠어" — 확인해보니 이 기능(`write_alarm_script()`의 Hue 블록, launchd 알람 스크립트가 음악 재생 전에 Hue 그룹 조명을 켬)은 이미 구현돼 있었다.

- **원인**: 스크립트가 `jq`를 `/usr/bin/jq`로 하드코딩했는데, 이 Mac엔 그 경로에 jq가 없다(anaconda 경로 `/opt/anaconda3/bin/jq`에만 있음) — 실측 `jq: command not found`. jq가 없으면 `HUE_IP`/`HUE_KEY`/`HUE_ROOM_ID`가 전부 빈 문자열이 되어 `if [ -n "$HUE_IP" ] ...` 조건이 항상 거짓으로 떨어지고, "Hue Command connection not found; music alarm continues" 분기로 조용히 넘어갔다. `log show`로 지난 알람 기록을 뒤져봐도 Hue 관련 로그가 전혀 없어서 발견(스크립트 자체는 여러 날 실행됐는데도 Hue 블록 흔적이 없었음).
- **수정**: `write_alarm_script()`가 스크립트 생성 시점에 `shutil.which("jq")`로 실제 경로를 찾아 `JQ` 변수로 스크립트에 박아 넣는다(하드코딩 대신). 5곳의 `/usr/bin/jq` 호출을 전부 `$JQ`로 교체.
- 검증: 수정된 스크립트의 Hue 블록을 그대로 떼어내 수동 실행 — `HUE_RESPONSE={"data":[...],"errors":[]}`로 실제 Hue Bridge 조명 그룹 전원 켜기 성공 확인.

## 38. 🔗 채용공고 표: 공고 원문 링크 + 준비할 점 검색 링크 (★ 2026-08-22 추가)

**사용자 요청**: "공고를 클릭하면 채용공고 사이트가 열리는 링크만들면 좋을거같아" / "준비할점도 링크화해서 관련 정보를 볼수있게 해줘".

`이직시스템/job_collector.py`의 `publish_email_job_summary_table()` 변경. 자세한 내용은 [이직시스템/README.md](../이직시스템/README.md)의 해당 절 참고 — 공고 제목 셀에 원문 채용공고 URL을, 준비할 점 셀에 그 문구로 구글 검색을 거는 URL을 건다.

## 39. 🎨 Muse Trace 점진 업그레이드 (★ 2026-08-24 추가)

예술작품용 웹캠 시선 추정 사이트 **Muse Trace**를 한 번 만들고 방치하지 않도록, Shift Alarm 최상위 메뉴에 2주 주기의 개선 체크 항목을 추가했다.

- 메뉴 제목에서 현재 단계, 전체 단계 수, 점검 필요 여부 또는 다음 점검일을 바로 확인한다.
- 하위 메뉴에서 공개 사이트를 열고 현재 초점과 전체 로드맵을 볼 수 있다.
- `✅ 이번 점검 완료 · 다음 단계로`를 누르면 완료 날짜를 설정 파일에 기록하고 다음 단계로 이동한다. 다음 점검일은 완료일로부터 14일 뒤다.
- 로드맵은 `측정 신뢰성 → 반복 가능한 실험 → 해석 지표 확장 → 관람자 집단 분석 → 작가 피드백 루프 → 동의·개인정보` 순으로 순환한다.
- 상태 키는 `muse_trace_upgrade_step`, `muse_trace_upgrade_last_review`이며 기존 `~/.shift_alarm_config.json`에 함께 저장된다. 처음 추가된 날에는 즉시 `점검 필요`로 표시해 첫 개선 작업을 시작할 수 있게 한다.

## 40. 추천 공고·경진대회 → Career Loop 연결 (★ 2026-08-24 추가)

Shift Alarm 메뉴와 Scriptable 위젯의 추천 공고·경진대회를 누르면 Notion을 직접 열지 않고 `https://career-loop-donggeun.pulpilisory.chatgpt.site/recommendation` 상세 화면으로 이동한다.

- `career_loop_recommendation_url()`이 현재 추천 상태의 제목·회사/주최자·점수·카테고리·마감·출처·원문 URL을 쿼리로 변환한다.
- 사이트 상세 화면에서 추천 판단, 지원/출전 전 준비사항, 확인 질문, 스터디 기록 연결을 먼저 보여준다.
- Notion 분석 주소는 삭제하지 않고 사이트 안의 `Notion 원본` 보조 링크로 전달한다.
- 앞으로 새로운 공고나 대회가 선정돼도 Shift Alarm 코드나 사이트를 항목별로 다시 수정하지 않고 같은 상세 화면을 사용한다.

## 38. 🔗 채용공고 표: 공고 원문 링크 + 준비할 점 검색 링크 (★ 2026-08-22 추가)

**사용자 요청**: "공고를 클릭하면 채용공고 사이트가 열리는 링크만들면 좋을거같아" / "준비할점도 링크화해서 관련 정보를 볼수있게 해줘".

`이직시스템/job_collector.py`의 `publish_email_job_summary_table()` 변경. 자세한 내용은 [이직시스템/README.md](../이직시스템/README.md)의 해당 절 참고 — 공고 제목 셀에 원문 채용공고 URL을, 준비할 점 셀에 그 문구로 구글 검색을 거는 URL을 건다.

## 41. 🧑‍🤝‍🧑 툴파챗 메뉴 항목 (★ 2026-08-24 추가)

**사용자 요청**: "이것도 shift alarm 에 항목만들어줘" (툴파챗을 가리킴).

- 툴파챗(`툴파챗/chatapp/`)은 Fly.io 대신 이 Mac + Cloudflare Quick Tunnel로 자체 호스팅한다(해당 프로젝트 README 참고) — 계정·도메인 없이 쓰는 Quick Tunnel이라 `cloudflared`가 재시작될 때마다(Mac 재부팅 등) URL이 바뀐다.
- 새 헬퍼 `get_tulpachat_url()`: 고정 URL을 저장하지 않고, `~/Library/Logs/tulpachat_tunnel.err.log`에서 가장 최근에 찍힌 `https://*.trycloudflare.com` 패턴을 정규식으로 찾아 매번 새로 반환한다 — 메뉴를 열 때마다 최신 URL을 보장한다.
- `build_menu()`의 "🎲 추천 사이트 열기" 바로 아래에 URL이 있을 때만 "🧑‍🤝‍🧑 툴파챗 열기" 항목을 추가한다(터널이 아직 안 떴으면 조용히 생략).

## 42. ⚠️ CPU 과부하 감지 알람 (★ 2026-08-25 추가)

**사용자 요청**: "앞으로 cpu 70%이상 과부화되는 상태로 30분이상 붙잡혀있거나 멈춰있는 프로세스가있으면 shift alarm 에서 항목으로 발견할수있게하고 인지하는즉시 맥알람 발생하게 해줘" — `replayd`/저장공간 스캔 프로세스가 몇 시간씩 CPU를 붙잡고 있었는데 아무 알림도 없이 넘어갔던 실사용 사례에서 나온 요청.

- 새 헬퍼 `_sample_high_cpu_processes(threshold=70.0)`: `ps -Ao pid,pcpu,comm`을 파싱해 threshold% 이상인 프로세스를 `(pid, comm, cpu)`로 반환. `comm` 필드에 공백이 들어있는 경로(`Codex Computer Use.app/...`)도 `split(None, 2)`로 안전하게 처리.
- 1분마다(`HIGH_CPU_CHECK_INTERVAL_SECONDS=60`) `_check_high_cpu`가 백그라운드 스레드에서 표본을 뜬다 — `ps` 호출이 느려질 가능성을 대비해 메인 스레드를 막지 않는다(AppKit 호출은 없으므로 안전, `build_menu`만 `AppHelper.callAfter`로 넘김).
- 상태는 `(pid, comm)` 키로 추적한다: 처음 70% 넘긴 시각을 기록해두고, **끊기지 않고** 30분(`HIGH_CPU_STUCK_MINUTES`) 이상 이어지면 그때 알람을 울린다. 한 번 울린 뒤로는 같은 "붙잡힘" 동안 다시 안 울리고, 프로세스가 threshold 밑으로 내려가거나 사라지면 추적을 리셋해서 다음에 다시 잡히면 처음부터 30분을 다시 센다.
- 알람은 `notify_spoken`(소리+음성, 예고 없는 알림 규칙에 맞음)으로 "⚠️ CPU 과부하 감지 · {프로세스명} — {cpu}%, {분}분째"를 알린다.
- 메뉴 최상단(급여 항목 바로 아래)에 걸린 프로세스가 있을 때만 "⚠️ CPU 과부하 프로세스 N개" 하위 메뉴가 뜨고, 각 프로세스의 이름·퍼센트·경과 시간·PID를 보여준다. 하위 항목에 "Activity Monitor 열기"도 추가.
- 검증: 실제 상태 전이 로직(추적 시작 → 29분(무음) → 31분(알람 1회) → 32분(재알림 없음) → 프로세스 소멸(추적 해제) → 재등장 시 처음부터 다시 30분)을 독립 시뮬레이션으로 확인. `_sample_high_cpu_processes()`도 실제 시스템에서 호출해 정상 파싱 확인(`fileproviderd`, `ApplicationsStorageExtension` 등 실제 고CPU 프로세스 정상 추출).

## 43. 🌡️ 메뉴바 열 상태 표시 + 요주의 프로세스 자동 종료 (★ 2026-08-25 추가)

**사용자 요청**: "맥북 온도 같은거 메뉴바 타이틀에 항상 띄울수없나?" / "니가 아까말한 두개 요주의 프로세스로 선정하고 필요없는 프로세스라고 판단하면 자동으로 킬하도록 파이프라인 구성해".

- **열 상태 표시**: `get_thermal_status()` — Apple Silicon은 sudo 없이 원시 온도(°C)를 읽을 방법이 없다. `powermetrics --samplers thermal`은 root를 요구하고, `osx-cpu-temp`(Homebrew) 같은 서드파티 도구도 실측 결과 `0.0°C`만 반환했다(Intel 전용 SMC 키 기반이라 Apple Silicon엔 그 키가 없음). 대신 `pmset -g therm`(sudo 불필요)이 보고하는 `CPU_Speed_Limit`(%) — macOS 자신이 열 때문에 CPU를 얼마나 줄였는지 판단하는 지표 — 를 쓴다. 41번 항목에서 추가한 1분 주기 CPU 표본 스레드에 얹어서 같이 갱신하고(`self._thermal_status`), 메뉴바 타이틀에 항상 "🌡️"(정상) 또는 빨간 "🌡️NN%"(스로틀링 중)로 표시한다.
- **요주의 프로세스 자동 종료**: `AUTO_KILL_HIGH_CPU_NAMES = {"replayd", "StorageManagementService", "ApplicationsStorageExtension"}` — 직전(42번 항목) CPU 과부하 조사 중 실제로 몇 시간씩 CPU를 붙잡고 있던 게 확인된 두 시스템 데몬만 화이트리스트로 담았다. **임의의 새로 붙잡힌 프로세스를 전부 자동 종료하지는 않는다** — 잘못하면 중요한 작업 중인 프로세스를 죽일 위험이 있어서, 사용자와 함께 "안전하게 죽여도 된다"고 확인한 것만 대상으로 범위를 좁혔다. 30분 이상 붙잡힌 게 확인되는 시점에 화이트리스트 소속이면 알림만 주는 대신 `os.kill(pid, SIGKILL)`로 바로 종료하고, 알림 문구도 "메뉴바에서 확인하세요" 대신 "자동 종료함"으로 바뀐다. 종료 후에는 추적 상태를 지워서, 그 데몬이 (macOS가 다시 띄워서) 나중에 또 붙잡히면 처음부터 새로 30분을 센다.
- 검증: `pmset -g therm` 파싱 실제 시스템에서 확인(`{'throttled': False, 'percent': 100}`). `os.kill(pid, signal.SIGKILL)` 메커니즘은 더미 `sleep` 프로세스로 별도 검증(실제 시스템 데몬을 테스트 목적으로 건드리지 않음).

## 44. 🔗 알림 클릭 시 관련 링크로 바로가기 (★ 2026-08-27 추가)

**사용자 요청**: "알람 뜰 때 Show 클릭하면 그거에 해당하는 내용을 볼 수 있으면 좋겠어 — 메일 알람이면 메일 링크로, 툴파챗 알람이면 툴파챗 링크로 바로가기가 되면 좋겠어".

- `notify_spoken()`에 `url=` 인자를 추가했다. 지정하면 `rumps.notification(..., data={"url": url})`로 실어보내고, 지정 안 하면(근무 알람·리마인더 등 원래부터 딱히 열 링크가 없는 알림) `data=None`으로 기존과 동일하게 동작한다.
- `ShiftAlarmApp`에 `@rumps.notifications` 핸들러(`_handle_notification_click`)를 새로 등록했다 — 사용자가 알림을 클릭("보기"/Show)하면 macOS가 이 핸들러를 부르고, 실려온 `data["url"]`을 기존 메뉴 링크 열기와 같은 방식(`_open_url` — Notion 링크는 Notion 앱으로, 그 외는 기본 브라우저로)으로 바로 연다. 이전엔 이 App 앱 인스턴스에 알림 클릭 핸들러 자체가 없어서 클릭해도 아무 반응이 없었다.
- 적용한 곳: 📧 새 메일 알림(`_gmail_message_url(top_item["id"])`로 해당 메일 본문 딥링크), 🧑‍🤝‍🧑 툴파챗 새 메시지 알림(`get_tulpachat_url()`). 다른 `notify_spoken()` 호출(근무 알람, 리마인더, 저장공간 부족, CPU 과부하 등)은 `url`을 안 넘기므로 클릭해도 그냥 닫히는 기존 동작 그대로다 — 필요해지면 같은 패턴으로 확장하면 된다.

## 45. 🔕 툴파챗 새 메시지 알림 축약 (★ 2026-08-28 추가)

**사용자 요청**: "shift alarm에서 툴파챗 메시지 알람 오는 거 너무 과한 거 같아, 간단하게 축약해서 '누구에게 메시지 옴' 이런 식으로만 알람 오게 해."

- 예전엔 메시지 내용 미리보기(최대 60자)를 화면에 띄우고 그대로 음성으로도 읽어서, 대화가 활발한 방에서는 알림이 계속 시끄러웠다. 이제는 발신자 이름만 짧게 알린다 — 예: "손무에게 메시지 왔어요", 여러 명이면 "손무 외 2명에게 메시지 왔어요"(발신자 기준으로 묶음, 메시지 건수 기준 아님). 내용은 앱에서 직접 확인.

## 46. ⏪ 절전 방지 "항상 켜기"를 근무 전후 1시간 창으로 되돌림 (★ 2026-08-29 되돌림)

**배경**: 8월 23일 커밋(c27babf, "Shift Alarm 실행 중 원격 접속 항상 유지")이 근무 전후 1시간에만 `caffeinate`를 켜던 로직을 지우고 무조건 켜기만 하도록 바꿨다. 그 결과 이 맥이 8월 23일부터 8월 29일까지 6일간 시스템 절전에 단 한 번도 들어가지 못했다(`caffeinate -i -s -t 2147483647`가 끊김 없이 계속 실행됨). 8월 28일 CPU 과열 문의에서 macOS 화면 시간 데몬 `replayd`가 82%까지 폭주하는 걸 발견했는데, 절전/기상 주기가 끊기면 이런 백그라운드 유지보수 데몬들이 정상적으로 몰아서 처리되지 못하고 계속 도는 것으로 의심돼(정황 증거, 100% 확정은 아님) 사용자가 "완전 원복"을 선택했다.

- `_check_stay_awake()`를 8월 23일 이전 방식으로 되돌렸다: `stay_awake_always`(수동 "항상 켜기" 토글) 켜져 있으면 항상, 아니면 `get_stay_awake_window()`(근무 전후 1시간)에 있을 때만 `start_caffeinate()`, 그 밖에는 `stop_caffeinate()`로 꺼서 맥이 정상적으로 잠들 수 있게 했다.
- 메뉴에서 사라졌던 "🌙 절전 방지 항상 켜기 (원격 접속용)" 수동 토글 항목(`toggle_stay_awake_always` 콜백)도 같이 복원했다 — 휴일에 밖에서 원격 접속하고 싶을 때 여전히 수동으로 켤 수 있다.
- 실측 확인: 이 되돌림을 적용하기 전 `~/.shift_alarm_config.json`의 `stay_awake_always`가 이미 `true`로 저장돼 있어서(그래서 계속 항상 켜짐 상태였음) `false`로 바꿔 저장한 뒤 재시작 — `caffeinate -i -s -t 2147483647` 프로세스가 실제로 사라지는 것까지 확인했다.

## 47. ⏰ GY→Swing 전환 휴무 첫날 기상 알람 18:00 (★ 2026-08-29 추가)

**사용자 요청**: "GY에서 Swing으로 넘어가는 휴일 첫날 알람을 오후 6시로 하자, 휴일에도 마치 근무하는 것처럼 할 거야 앞으로는."

- 기존 "Day→GY 전환 휴무일 기상 알람 08:00"(36번 항목)과 같은 패턴이지만, 그쪽은 휴무 블록 전체(며칠이든)에 적용되는 반면 이번 요청은 명시적으로 "휴일 첫날"만 지정했다 — `_is_gy_to_swing_off_day()`는 그 휴무 블록의 첫 번째 날짜에만 True를 반환하고, 둘째 날부터는 평소처럼 알람 없는 휴무로 되돌아간다.
- `_set_shift_internal()`(근무표 자동 적용이 매일 자정 이걸 호출)과 "현재 설정 보기" 알림창 양쪽에 새 분기를 추가했다 — 앞으로 이 전환이 있을 때마다 사람이 수동으로 안 챙겨도 자동 적용된다.
- 실측 검증: 오늘(2026-08-29)이 마침 이 전환의 첫 휴무일이라, 재시작 직후 `com.shfitalarm.music.plist`의 `StartCalendarInterval`이 실제로 `{Hour: 18, Minute: 0}`으로 반영된 것까지 확인했다.

## 48. 📊 저장공간 상세 보기 — 홈 폴더 용량 순위 (★ 2026-08-29 추가)

**사용자 요청**: 대화 중 직접 만들어준 "System Data 용량 순위" 표를 보고 "이거 shift alarm에서 볼 수 있게 항목 만들어줘."

- 메뉴에 "📊 저장공간 상세 보기 (용량 순)" 항목 추가 — 누르면 `~`(홈 폴더) 바로 아래 항목들을 용량 큰 순서로 스캔해 상위 12개를 보여준다.
- `du`를 subprocess로 부르지 않고 순수 파이썬 `os.walk`로 직접 합산한다(`scan_top_level_sizes`/`_dir_size_bytes`) — 7번 항목(휴지통 용량)에서 이미 겪은 것과 같은 이유로, launchd가 띄운 실제 메뉴바 프로세스에서는 `subprocess(capture_output=True)`가 조용히 실패할 수 있기 때문이다.
- 파일이 많으면 스캔에 수십 초~2분 정도 걸릴 수 있어 백그라운드 스레드에서 돌리고, 시작할 때 "스캔 중" 음성 알림을 먼저 주고 끝나면 `rumps.alert` 결과 창을 띄운다(AppKit 메인 스레드 규칙에 맞춰 `AppHelper.callAfter`로 마샬링).
- 실측: 독립 실행으로 106초 걸려 Library(49.6GB)·Desktop(27.1GB)·.codex(5.2GB) 등을 정확히 큰 순서로 반환하는 것 확인.

★ 후속 버그 수정(같은 날): 스캔이 1~2분 걸리는 동안 사용자가 다른 앱으로 넘어가 있으면 `rumps.alert()` 결과 창이 그 뒤에 조용히 떠서 "아무것도 안 보인다"는 신고를 받았다. `rumps.notification()` 배너를 먼저 띄워 완료를 놓치지 않게 하고, `rumps.alert()` 대신 `NSAlert`를 직접 만들어 `activateIgnoringOtherApps_` + `NSModalPanelWindowLevel`로 다른 앱 창 뒤에 숨지 않게 강제했다 — 이 파일의 다른 NSPanel 프롬프트에서 이미 검증된 것과 같은 패턴.

## 49. 🔕 메뉴바 타이틀 리마인더 — 체크 안 한 항목만 표시 (★ 2026-08-29 추가)

**사용자 요청**: "리마인더용 이모지가 너무 많이 타이틀에 뜨는데 체크안된 리마인더 항목만 위에 뜨게 해."

- `get_today_reminder_title_tokens()`에 `checklist_state` 인자를 추가했다 — 이미 메뉴 드롭다운(`_build_reminder_status_menu_items`)에서 ✅/⬜ 표시에 쓰던 `self._checklist_state`({라벨: checked})를 그대로 재사용해서, 오늘 리마인더 중 이미 체크한 항목은 타이틀 아이콘 나열에서 뺀다. 드롭다운 메뉴 쪽 표시는 그대로(체크된 것도 ✅로 계속 보임) — 타이틀만 "아직 안 한 일"로 좁힌 것.
- `_update_title()` 호출부만 `checklist_state=self._checklist_state`를 넘기도록 고쳤고, 그 외 축약 로직(`_compress_title_reminders`, `_adapt_title_if_hidden`)은 그대로 재사용된다.

## 50. 🎬 일본어 자막 추출 완료 알림 (★ 2026-08-29 추가)

**사용자 요청**: "여태까지는 자막 추출 완성되었다는 알람 없었는데 자막 추출이 다 되면 shift alarm에서 알람 발생하게 해주면 좋겠어."

- `whisper_series_stream.sh`/`subtitle_notion_epub_only.sh`는 새 iTerm 창(`open -a iTerm`)에서 돌기 때문에, shift_alarm이 `subprocess.Popen`으로 부른 원래 프로세스는 iTerm을 띄우자마자 바로 끝나버려서 완료 시점을 알 방법이 없었다.
- 실행마다 `JP_SUBTITLE_RUN_ID`(uuid) 환경변수를 넘기고, 두 스크립트 모두 실제 작업이 끝나면 `/tmp/_jp_subtitle_run_<id>.done` 마커 파일을 남기도록 고쳤다. shift_alarm은 `_watch_jp_subtitle_completion()`을 백그라운드 스레드로 띄워 15초 간격으로 마커를 폴링하다가 발견하면 `notify_spoken()`으로 완료 알림(소리+음성)을 띄우고 마커를 지운다. 최대 3시간까지 기다리고 그 이후엔 조용히 포기(무한정 스레드가 안 남게).
- `run_jp_subtitle_extraction()`(연달아)과 `run_jp_subtitle_stage2_only()`(자막만) 둘 다 적용. `run_jp_workout_extraction_only()`(운동용 영상만, 자막 없음)는 대상 아님 — 이미 자체 Terminal 창에 완료 로그를 찍고 자막 파이프라인과 무관한 별개 기능이라 이번 범위에서 제외.
- 메뉴에서 직접 스크립트를 손으로 실행(shift_alarm 경유 안 함)하면 `JP_SUBTITLE_RUN_ID`가 비어있으므로 마커를 안 남기고 조용히 기존 동작 그대로 동작한다.

## 51. 🐾 Shift Alarm Pet — 반투명 + 클릭 애니메이션 + 클릭 시 실제 메뉴 표시 (★ 2026-08-29 추가)

**사용자 요청**: "codex pet처럼 클릭하면 움직인다던가 하는식으로 좀 ui 꾸미면좋겠고 이거 사각형이 좀 반투명 했으면 좋겠어 그리고 클릭하면 shift alarm의 항목이 보여서 클릭이 가능했으면 좋겠어."

- **반투명**: 배경 사각형 alpha를 0.92 → 0.55로 낮춤(`drawRect_`).
- **클릭 애니메이션**: `ShiftAlarmPet._bounce()` — `NSAnimationContext.runAnimationGroup_completionHandler_`로 panel의 frame을 0.08초 만에 살짝(가로+8/세로+6) 부풀렸다가, 완료 콜백에서 0.10초 만에 원래 크기로 되돌린다. 저장된 좌표(`petDidMove()`가 다루는 `pet_x`/`pet_y`)는 건드리지 않는다 — 애니메이션이 끝나면 정확히 원래 frame으로 복귀.
- **클릭 시 실제 메뉴 표시**: 기존엔 클릭하면 `show_status()`(현재 설정 알림창)만 떴는데, 이제 `self.app.menu._menu`(rumps가 관리하는 실제 NSMenu — 메뉴바 아이콘의 그 메뉴와 완전히 동일한 객체)를 `NSMenu.popUpMenuPositioningItem_atLocation_inView_`로 Pet 바로 위에 띄운다. 메뉴 안의 모든 항목(리마인더 체크, 자막 추출 실행 등)이 그대로 클릭 가능해졌다. "현재 설정 확인"은 `기타` 하위메뉴에 남아있어 여전히 접근 가능.

## 52. 🎬 운동용 영상만 추출도 완료 알림 추가 (★ 2026-08-29 추가)

**사용자 요청**: "운동용 영상만, 자막 없음 도 알람 기능 있게 해" (50번 항목의 자막 추출 완료 알림을 이 기능에도 확장해달라는 요청).

- `run_jp_workout_extraction_only()`는 파이썬이 직접 `.command` 런처를 생성하는 구조라, 별도 셸 스크립트를 고칠 필요 없이 job_status 판정 직후 같은 마커 파일(`/tmp/_jp_subtitle_run_<id>.done`)을 쓰는 줄만 추가했다. `_watch_jp_subtitle_completion()`(50번 항목에서 만든 공용 폴링 함수)을 그대로 재사용해서 완료되면 "운동용 영상만 추출 완료" 알림이 뜬다.

## 53. 🐾 Shift Alarm Pet — 말풍선 재설계 + 이미지 전용 클릭 + 카드 순환 (★ 2026-08-29 추가)

**사용자 요청**: 이어진 여러 요청 — "펫그림을 누를때만 클릭이 되면 좋겠어, 글자들은 펫이 말하는것처럼 말풍선위에 글자로", "펫의 배경이 반투명한 검은색인데 이 배경 자체가 없어도될거같아", "말풍선에 저장용량이라던지 리마인더는 표기가 안되는거같은데 30초 단위로 말풍선을 바꾸면서 표기하면 좋겠어". 51번 항목(반투명 배경+클릭 애니메이션+메뉴 표시)을 이 항목이 대체한다.

- **배경 제거 + 말풍선 분리**: 이미지+텍스트를 한 사각형에 감싸던 기존 디자인을 버렸다. 이제 이미지(`IMAGE_RECT`, 배경 없이 그대로)와 말풍선(`BUBBLE_RECT`, 꼬리 달린 둥근 사각형)을 완전히 분리해서 그린다. Pet 전체 크기도 326×76 → 210×120(이미지 아래, 말풍선 위)으로 바꿨다.
- **이미지 전용 클릭 판정**: `mouseUp_`이 `event.locationInWindow()`를 뷰 좌표로 변환해 `IMAGE_RECT` 안에서 뗀 클릭일 때만 `petWasClicked()`(메뉴 팝업)를 부른다 — 말풍선이나 빈 공간을 눌러도 반응 안 함. 드래그는 기존대로 어디서 시작해도 동작(사용성 유지).
- **카드 순환**: shift_alarm이 `(제목, 내용)` 카드 리스트(근무·저장공간·오늘 리마인더·AI 사용량·[열 상태 있을 때만])를 `_update_title()`에서 만들어 `shift_pet.update(cards)`로 넘긴다. Pet 안의 `NSTimer`(`CARD_ROTATE_SECONDS=30`)가 30초마다 다음 카드로 자동으로 넘긴다 — 말풍선 한 칸엔 두 줄만 들어가서 여러 정보를 동시에 못 보여주던 문제 해결. `ShiftAlarmPet.update()`의 시그니처가 `(headline, usage)` → `(cards)`로 바뀌었다(기존 51번 항목의 2-인자 시그니처 폐기).

## 54. 💡🎵 Hue 거실 불끄기 시 재생 중인 음악 일시정지 (★ 2026-08-29 추가)

**사용자 요청**: "휴 거실 1 불끄기 눌렀을때 만약에 맥에서 재생되고있는 음악이있다면 일시정지하게끔 하면 좋겠어."

- Elmedia(Mac App Store 샌드박스 빌드)는 표준 AppleScript `pause` 동사가 없어(8-1/33번 항목에서 이미 확인된 제약) 앱별 제어 대신 시스템 전체 재생/일시정지 미디어 키(`NX_KEYTYPE_PLAY`, `NSEvent`+`Quartz.CGEventPost`로 posts)를 누른다 — 어떤 플레이어든 상관없이 동작.
- 이 키는 토글이라 재생 중이 아닐 때 누르면 오히려 재생을 시작시켜버릴 수 있다. 그래서 `_is_elmedia_playing()`(write_alarm_script의 자가검증과 같은 휴리스틱 — 정적 텍스트에 "Elapsed Time"이 있으면 재생 중)으로 실제 재생 중인지 먼저 확인한 뒤에만 누른다.
- `_toggle_hue_thread()`에서 `toggle_hue_room()`이 꺼짐(`is_on=False`)을 반환했을 때만 `pause_music_if_playing()`을 부른다 — 조명을 켤 때는 음악을 건드리지 않는다.
- 실측 확인: 코드 배포 시점에 실제로 Elmedia가 곡을 재생 중이었고(`osascript`로 "Elapsed time: eleven seconds" 등 정적 텍스트 확인), `_is_elmedia_playing()` 휴리스틱이 이를 정확히 감지하는 것까지 확인했다(실제 미디어 키 전송·조명 토글 자체는 사용자 실사용 중 방해하지 않기 위해 라이브로 트리거하지 않음).

## 55. ✅ 일일 루틴 "전부 체크"를 하위 메뉴 밖으로 (★ 2026-08-30 추가)

**사용자 요청**: "일일 루틴 체크시트에서 전부체크하기는 화살표 들어가는게아니라 항목 밑에서 바로 클릭할수있게 해줘."

- 예전엔 "🌅 일일 루틴 체크리스트" 하위 메뉴(화살표로 들어가야 하는 서브메뉴) 맨 위에 "✅ 전부 체크"가 있어서, 한 번 더 눌러 들어가야만 보였다.
- 이제 그 하위 메뉴 항목 바로 아래, 최상위 메뉴 레벨에 "✅ 일일 루틴 전부 체크"로 뺐다 — 하위 메뉴를 열지 않고 바로 클릭 가능. 미체크 항목이 하나도 없으면(전부 체크된 상태) 표시 안 함(기존 동작 그대로 유지).
