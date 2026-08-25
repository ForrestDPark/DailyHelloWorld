# 툴파시스템 채팅앱

`툴파시스템/`에 만든 페르소나들이 한 채팅방에서 나(사용자)와, 그리고 서로와 대화하는
그룹챗 웹앱. 핸드폰 브라우저에서 접속해서 쓸 수 있게 되어 있다.

## 왜 이런 구조인가 (읽고 시작할 것)

**서버·워커 전부 이 Mac에서 돌고, Cloudflare Tunnel로 인터넷에 노출한다.**
★ 2026-08-24: 원래는 서버를 Fly.io(클라우드)에, 워커만 Mac에 두는 구조였다 —
AI 응답 생성에 쓰는 `claude -p`/`codex exec` CLI 로그인 정보를 공개 서버로
옮기고 싶지 않아서였다. 그런데 Fly.io 무료 체험이 끝나 카드 등록을 요구해서,
"Fly.io 없이 만들 수 없냐"는 요청으로 전부 이 Mac에서 도는 구조로 바꿨다.
카드·클라우드 비용이 전혀 없고, 서버와 워커가 같은 기기라 예전처럼 HTTP로
멀리 오가지 않고 `localhost`로 바로 통신해 더 빠르다.

트레이드오프: **이 Mac이 켜져 있고 인터넷에 연결돼 있어야만 앱이 동작한다**
(Fly.io처럼 Mac이 꺼져 있어도 클라우드에서 계속 떠 있는 방식이 아니다).

- **서버(`server/`)**: FastAPI, `127.0.0.1:8000`에서만 리슨(LAN에 직접 노출 안
  함 — 외부 접속은 전부 Cloudflare Tunnel을 거친다). 채팅 메시지·"이 페르소나가
  응답할 차례" 대기열을 SQLite(`~/.tulpachat/chatapp.db`)에 저장. AI 호출 코드는
  없다.
- **워커(`worker/`)**: 서버를 몇 초마다 폴링해서 대기열을 가져오고, 이미
  로그인된 CLI로 응답을 생성해 서버에 돌려보낸다. 페르소나 프로필은 Notion
  (`https://www.notion.so/3c632a1eae8080a581eed393294c097a`)에서 주기적으로
  읽어온다.
- **Cloudflare Tunnel**: `cloudflared tunnel --url http://localhost:8000`으로
  로컬 서버를 공개 HTTPS 주소에 연결한다. 계정·도메인 없이 쓰는 "Quick
  Tunnel"이라 **cloudflared가 재시작되면(Mac 재부팅 등) URL이 매번 바뀐다** —
  자세한 확인 방법은 아래 "URL 확인하기" 참고.
- 워커가 안 켜져 있으면 채팅방에 메시지는 쌓이지만 페르소나는 응답하지 않는다
  (사용자 메시지는 정상 저장됨 — 워커가 다시 켜지면 밀린 대기열부터 처리).

## 폴더 구조

```
chatapp/
  server/               # FastAPI 서버 (이 Mac에서 127.0.0.1:8000으로 실행)
    app.py                # API + 정적 파일 서빙 + Basic 인증
    db.py                 # SQLite 스키마
    requirements.txt
  worker/               # 이 Mac에서 계속 돌리는 폴링 워커
    persona_worker.py     # 메인 루프
    notion_personas.py     # Notion에서 페르소나 프로필 읽기
    ai_exec.py              # codex→claude 폴백 실행 (이직시스템과 동일 파일)
  static/               # 채팅 UI (바닐라 HTML/CSS/JS, 프레임워크 없음)
    index.html / chat.js / style.css
```

## launchd로 상시 구동 (server / tunnel / worker 3개)

`shift_alarm.py`와 같은 방식으로 LaunchAgent 3개가 등록돼 있다 — 재부팅해도
자동으로 뜨고, 크래시하면 launchd가 다시 살린다(`KeepAlive.SuccessfulExit=false`).

| Label | 역할 | plist |
|---|---|---|
| `com.tulpachat.server` | FastAPI 서버 (127.0.0.1:8000) | `~/Library/LaunchAgents/com.tulpachat.server.plist` |
| `com.tulpachat.tunnel` | Cloudflare Quick Tunnel | `~/Library/LaunchAgents/com.tulpachat.tunnel.plist` |
| `com.tulpachat.worker` | AI 응답 생성 워커 | `~/Library/LaunchAgents/com.tulpachat.worker.plist` |

로그는 각각 `~/Library/Logs/tulpachat_{server,tunnel,worker}.{out,err}.log`.
코드를 고친 뒤에는 `launchctl kickstart -k gui/$(id -u)/com.tulpachat.<label>`로
재시작해야 반영된다. 순서상 server → tunnel → worker 순으로 띄우는 게 안전하다
(tunnel이 뜰 때 server가 이미 응답해야 하고, worker는 server만 있으면 됨).

서버 환경변수(`com.tulpachat.server.plist`의 `EnvironmentVariables`):
`CHATAPP_DB_PATH`, `APP_USERNAME`/`APP_PASSWORD`(접속 비밀번호), `WORKER_TOKEN`
(워커 인증, 워커 plist의 `CHATAPP_WORKER_TOKEN`과 반드시 동일해야 함),
`GROUP_ROOM_ENABLED`.

## URL 확인하기

Quick Tunnel은 재시작마다 새 URL(`https://<임의단어4개>.trycloudflare.com`)을
받는다. 현재 URL은 tunnel 로그 첫 부분에 찍힌다:

```bash
grep -A2 "quick Tunnel has been created" ~/Library/Logs/tulpachat_tunnel.err.log | tail -3
```

매번 바뀌는 게 불편하면(북마크가 안 됨) 나중에 Cloudflare 계정 + 소유한
도메인으로 "이름 있는 터널"을 만들어 고정 주소로 바꿀 수 있다 — 지금은
범위 밖으로 남겨둔다.

## 로컬에서 먼저 테스트

```bash
cd chatapp
python3 -m uvicorn server.app:app --reload --port 8000
# 다른 터미널에서
open http://localhost:8000
```

워커도 로컬에서 그대로 켜서 테스트할 수 있다(`CHATAPP_SERVER_URL`이 기본값
`http://localhost:8000`이라 별도 설정 없이 됨):

```bash
cd chatapp/worker
python3 persona_worker.py
```

## 배포 전 필수: Notion 통합 공유

워커가 페르소나 프로필을 읽으려면 `jp_subtitle_notion_token`(이직시스템 등에서
이미 쓰는 것과 같은 Notion 통합)이 **툴파시스템 페이지에도 연결돼 있어야 한다.**
Notion에서 툴파시스템 메인 페이지 → `...` 메뉴 → Connections → 해당 통합 추가.
(공유 안 해두면 워커가 `HTTPError: 404`로 실패한다 — 실제로 이렇게 확인했음.)

## 접속 비밀번호 (Basic 인증) — 필수

★ 2026-08-24: 처음엔 앱이 인증 없이 완전히 공개돼 있었고, 실제로 URL을 아는
지인이 들어와서 채팅을 어지럽힌 사고가 있었다. `APP_USERNAME`/`APP_PASSWORD`
가 둘 다 설정되면 `/api/worker/*`를 제외한 모든 요청에 HTTP Basic 인증이
걸린다(브라우저가 표준 로그인 팝업을 띄운다 — 한 번 입력하면 그 브라우저에서는
계속 기억됨). 워커는 별도 `WORKER_TOKEN`으로 인증하므로 이 비밀번호와 무관하게
계속 동작한다.

★ 같은 날 추가: 소유자 계정(`APP_USERNAME`/`APP_PASSWORD`, 지금은
`pulpilisory`)만 쓰기(채팅) 가능하고, **그 계정과 정확히 일치하지 않는 다른
아이디/비밀번호는 무엇을 입력하든 읽기 전용으로 통과**된다(별도 뷰어 계정을
미리 만들어둘 필요 없음). 읽기 전용 상태에서 메시지를 보내면 403으로 막힌다.

## 전체 채팅방 (당분간 폐쇄됨)

★ 2026-08-24: 전체 채팅방은 아무도 안 부르면 페르소나 전원이 매번 동시에
반응하는 구조라 거의 똑같은 답이 몇 개씩 쏟아지고, 서로 일면식 없어야 할
인물들이 Notion에 없는 친분·약속을 지어내는 문제가 실사용 중 확인됐다.
`GROUP_ROOM_ENABLED=false`(서버 plist)로 방 목록에서 숨기고 새 메시지도
거부하는 중 — 1:1 방은 전혀 영향 없다. 재개하려면 그룹 대화 로직(예: 매번
전원 응답 대신 관련 있는 인물만 반응하게, 서로 모르는 인물끼리는 그 사실을
인지하게)을 먼저 고친 뒤 `"true"`로 바꾸고 서버를 재시작한다.

## 화면 표시: "(가상)" 라벨

★ 2026-08-24: 실제 인물이 아니라 AI 페르소나라는 걸 항상 인지할 수 있게, 방
목록·채팅방 제목·메시지 발신자에 캐릭터 이름 뒤 "(가상)"을 붙여서 표시한다
(`static/chat.js`의 `displayName()`). 서버·워커가 매칭·프롬프트에 쓰는 실제
이름은 그대로 두고 화면 표시에만 적용했다.

## 페르소나 그룹화

★ 2026-08-25: "페르소나 목록도 그룹화하는 게 좋을거같아" 요청 — 페르소나
Notion 프로필에 `- 그룹: OOO` 줄을 추가하면 방 목록에서 그 이름으로 묶여
보인다(`worker/notion_personas.py`의 `extract_group()`이 파싱 →
`server`의 `personas.group_name` → `static/chat.js`의 `groupRooms()`).
그룹이 없으면 "그룹 없음"으로 모여 맨 아래에 정렬된다. 전체 채팅방은
그룹 구분 없이 항상 최상단.

지금 구성: **예술가부흥프로젝트**(동찬이형, 양승윤), **프로그램개발그룹**
(박정민, 박지환, 이천영, 한경호 선생님).

## 그룹 회의방

★ 2026-08-25: "동찬이형이랑 양승윤 그룹채팅방 만들고, 한경호선생님·박지환·
박정민·이천영 묶어서 그 안에서 회의하는 식으로" 요청 — 그룹명 자체가 방
하나로도 노출된다(`server/app.py`의 `list_rooms()`가 `is_group_room=True`로
표시, `room_id`=그룹명). 이 방에 메시지를 보내면 그 그룹 소속 페르소나
전원이 순서대로 응답한다 — `@이름`으로 특정 인물만 부를 수도 있다(전체
채팅방과 같은 규칙).

- **"회의"처럼 이어지는 이유**: 워커의 폴링 큐(`/api/worker/pending`)는
  한 번에 하나씩 처리한다. 첫 번째로 응답한 페르소나의 메시지가 즉시
  DB에 저장되므로, 다음 순서 페르소나가 컨텍스트를 가져올 땐 이미 앞선
  답변까지 포함돼 있다 — 별도의 체이닝 로직 없이 순차 처리 구조 자체가
  자연스러운 순서 있는 대화를 만든다.
- 이전에 폐쇄한 "전체 채팅방"(모든 페르소나가 뒤섞인 방)과 다르다 — 그룹
  회의방은 **실제로 서로 아는 사이인 사람들**끼리만 묶이므로(그룹 자체가
  그런 관계를 나타냄), 서로 모르는 인물이 친한 척 없는 친분을 지어내던
  문제가 구조적으로 줄어든다.
- 방 목록에서 그룹 회의방은 "👥 그룹명"으로 표시되고, 소속 페르소나들의
  그룹 헤더 섹션과는 별개로(그 그룹의 "구성원"처럼 묶이지 않게) 맨 위
  전체 채팅방 옆에 노출된다(`static/chat.js`의 `groupRooms()`).

## 담당 프로젝트 컨텍스트 (페르소나가 실제 코드 프로젝트를 알게 하기)

★ 2026-08-25: "동찬이형이랑 대화하면서 muse trace 아이디어를 냈는데, 채팅에서
그 프로젝트 현재 상태·문제점을 지적하며 대화를 이어갈 수 있지 않을까"라는
아이디어를 일반화한 기능. 페르소나 Notion 프로필에
`- 담당 프로젝트: 이직시스템, shift_alarm`처럼 이 저장소(`DailyHelloWorld_`)의
프로젝트 폴더명을 콤마로 나열해두면, 워커가 5분 동기화 주기마다 각 프로젝트의
`README.md`를 찾아 발췌(`PROJECT_README_MAX_CHARS=3000`자/프로젝트)해서
시스템 프롬프트에 포함시킨다(`worker/notion_personas.py`의 `extract_projects()`
+ `worker/persona_worker.py`의 `load_project_context()`). 페르소나는 이
정보를 근거로만 프로젝트 이야기를 하도록 지시받는다(README에 없는 내용을
지어내지 말 것).

- 프로젝트 폴더명은 정확히 저장소 루트 기준 폴더명과 일치해야 한다(예:
  `이직시스템`, `shift_alarm`, `MuseTrace` — 대소문자·언더스코어까지).
  `CLAUDE.md`의 "운영 중인 주요 프로젝트" 목록과 맞춰두면 헷갈리지 않는다.
- README가 없거나 못 읽으면 그 프로젝트만 "(README.md를 찾지 못함)"으로
  표시되고 나머지는 정상 처리된다 — 한 프로젝트 문제로 전체가 비지 않는다.
- 담당 프로젝트가 여러 개면(예: 한경호 선생님이 7개를 전부 담당) 프롬프트가
  꽤 길어진다(실측 ~18,000자) — 응답이 느려질 수 있다는 점 감안. 필요하면
  `PROJECT_README_MAX_CHARS`를 줄이거나 담당 프로젝트를 나눠라.
- 지금 구성: 한경호 선생님(전체 7개 프로젝트 코칭), 박정민(이직시스템·
  경진대회시스템), 박지환(손자병법·일본어공부), 이천영(shift_alarm·
  일본어자막추출).

## 사용법

1. 핸드폰 브라우저로 현재 tunnel URL(위 "URL 확인하기" 참고) 접속하면
   카카오톡처럼 **방 목록**이 먼저 뜬다 — 페르소나별 1:1 방(전체 채팅방은
   당분간 폐쇄).
2. 방을 눌러 들어가서 메시지를 보낸다. 방 자체가 그 인물이므로 `@` 없이
   보내도 항상 그 사람만 응답한다.
3. 페르소나 프로필을 Notion에서 고치면, 워커가 5분 주기로 다시 읽어와 반영한다
   (`PERSONA_SYNC_INTERVAL_SECONDS`).
4. **대화 내용은 10분 주기로 자동으로 Notion에 반영된다** — 한 인물이 등장한
   새 메시지가 4개 이상 쌓이면, 워커가 그 구간을 AI로 짧게 요약해서 그 인물
   페이지의 "함께 만든 이야기" 섹션에 날짜와 함께 추가한다
   (`STORY_SYNC_INTERVAL_SECONDS`, `STORY_SYNC_MIN_NEW_MESSAGES`). 잡담만
   있었으면 기록하지 않는다.

## 로드맵 / 알려진 제약

- **Quick Tunnel URL이 재시작마다 바뀐다** — 고정 주소가 필요해지면 Cloudflare
  계정 + 도메인으로 이름 있는 터널을 만든다.
- **페르소나끼리 자동으로 서로 계속 이어 대화하지는 않는다** — 사용자 메시지 1건당
  대상 페르소나가 한 번씩만 응답한다.
- 여러 페르소나가 동시에 응답 대상이면 워커가 순차 처리한다(폴링 루프가
  한 번에 하나씩 가져옴) — 응답이 조금씩 늦게 순서대로 뜬다.
- Notion 이야기 자동 기록은 요약 하나당 AI 호출 1번이 추가로 든다. 대화가
  아주 활발하면 10분마다 인물 수만큼 추가 호출이 생길 수 있다는 점 감안.
