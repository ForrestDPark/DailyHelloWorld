# 툴파시스템 채팅앱

`툴파시스템/`에 만든 페르소나들이 한 채팅방에서 나(사용자)와, 그리고 서로와 대화하는
그룹챗 웹앱. 핸드폰 브라우저에서 접속해서 쓸 수 있게 클라우드에 배포한다.

## 왜 이런 구조인가 (읽고 시작할 것)

**AI 응답은 클라우드가 아니라 항상 사용자의 Mac에서 생성된다.** 채팅 UI·메시지
저장·페르소나 프로필 캐시는 클라우드에 배포된 `server/`가 맡지만, 실제 페르소나
응답 생성은 `worker/persona_worker.py`가 Mac에서 직접 `claude -p`/`codex exec`
CLI(이직시스템의 `ai_exec.py`와 동일한 패턴)를 호출해서 만든다.

이렇게 나눈 이유는 하나다 — Claude/Codex CLI의 로그인 인증 정보를 공개
인터넷에 노출된 서버로 옮기고 싶지 않아서다. 그래서:

- **클라우드 서버(`server/`)**: 채팅 메시지·"이 페르소나가 응답할 차례" 대기열을
  SQLite에 저장. AI 호출 코드가 아예 없다.
- **Mac 워커(`worker/`)**: 서버를 몇 초마다 폴링해서 대기열을 가져오고, 이미
  로그인된 CLI로 응답을 생성해 서버에 돌려보낸다. 페르소나 프로필은 Notion
  (`https://www.notion.so/3c632a1eae8080a581eed393294c097a`)에서 주기적으로
  읽어온다.
- 이 워커가 안 켜져 있으면 채팅방에 메시지는 쌓이지만 페르소나는 응답하지 않는다
  (사용자 메시지는 정상 저장됨 — 워커가 다시 켜지면 밀린 대기열부터 처리).

## 폴더 구조

```
chatapp/
  server/               # 클라우드에 배포되는 FastAPI 서버
    app.py                # API + 정적 파일 서빙
    db.py                 # SQLite 스키마
    requirements.txt
  worker/               # Mac에서 계속 돌리는 폴링 워커
    persona_worker.py     # 메인 루프
    notion_personas.py     # Notion에서 페르소나 프로필 읽기
    ai_exec.py              # codex→claude 폴백 실행 (이직시스템과 동일 파일)
  static/               # 채팅 UI (바닐라 HTML/CSS/JS, 프레임워크 없음)
    index.html / chat.js / style.css
  Dockerfile
  fly.toml              # Fly.io 배포 설정
```

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

## 클라우드 배포 (Fly.io)

1. `brew install flyctl` 후 `fly auth login`으로 본인 계정 로그인.
2. `fly.toml`의 `app = "tulpa-chatapp"`을 전역으로 유일한 이름으로 바꾼다
   (예: `tulpa-chatapp-<본인아이디>`).
3. 볼륨 생성(SQLite 데이터 유지용): `fly volumes create chatapp_data --size 1 --region nrt`
4. 워커-서버 인증 토큰을 정해서 시크릿으로 등록:
   `fly secrets set WORKER_TOKEN="$(openssl rand -hex 24)"`
   (이 값을 적어두고, 나중에 Mac 워커의 `CHATAPP_WORKER_TOKEN` 환경변수에도 그대로 넣는다.)
5. `fly deploy`
6. 배포된 URL(`https://<app이름>.fly.dev`)이 곧 핸드폰에서 접속할 주소다.

## Mac 워커를 항상 켜두기 (launchd)

`shift_alarm.py`와 같은 방식으로 LaunchAgent를 등록해 재부팅해도 자동으로 뜨게
할 수 있다. 아직 plist는 만들지 않았다 — 필요하면 다음 세션에서 다음을 참고해
`shift-alarm-dev` 에이전트가 쓰는 것과 같은 패턴(`launchctl bootstrap`,
`StandardOutPath`/`StandardErrorPath` 로그, `-u` 언버퍼링 플래그)으로 만든다.
환경변수는 plist의 `EnvironmentVariables`에 넣는다:

```xml
<key>EnvironmentVariables</key>
<dict>
  <key>CHATAPP_SERVER_URL</key><string>https://<app이름>.fly.dev</string>
  <key>CHATAPP_WORKER_TOKEN</key><string>(위에서 만든 토큰)</string>
</dict>
```

당장은 그냥 터미널에서 `python3 worker/persona_worker.py`를 실행해두고 테스트해도 된다.

## 사용법 (배포·워커 실행 후)

1. 핸드폰 브라우저로 `https://<app이름>.fly.dev` 접속.
2. 메시지를 입력해서 보낸다. 아무도 지목하지 않으면 방에 있는 페르소나 전원이
   한 번씩 응답한다. `@이름`으로 특정 인물만 부를 수도 있다.
3. 페르소나 프로필을 Notion에서 고치면, 워커가 5분 주기로 다시 읽어와 반영한다
   (`PERSONA_SYNC_INTERVAL_SECONDS`).

## 로드맵 / 알려진 제약

- **페르소나끼리 자동으로 서로 계속 이어 대화하지는 않는다** — 사용자 메시지 1건당
  대상 페르소나가 한 번씩만 응답한다. 진짜 "페르소나끼리 무한히 대화 이어가기"를
  만들려면 폭주 방지(최대 턴 수, 종료 조건)를 먼저 설계해야 한다.
- 여러 페르소나가 동시에 응답 대상이면 워커가 순차 처리한다(폴링 루프가
  한 번에 하나씩 가져옴) — 응답이 조금씩 늦게 순서대로 뜬다.
- 대화 내용이 Notion의 "함께 만든 이야기" 섹션에 자동으로 요약되지는 않는다.
  지금은 대화가 끝난 뒤 Claude Code 세션에서 수동으로 요약해 넣어야 한다.
- 채팅방은 지금 하나뿐이다(모든 페르소나가 한 방에 같이 있음). 페르소나별
  1:1 방을 분리하고 싶다면 `room_id` 개념을 messages/pending_turns 테이블에
  추가해야 한다.
