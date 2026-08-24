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

앱 이름은 `fly.toml`에 이미 `tulpa-chatapp-pulpilisory`로 정해 두었다(전역 유일 이름 필요).

1. `brew install flyctl`(완료됨) 후 `fly auth login`으로 본인 계정 로그인(브라우저 인증 —
   반드시 사용자가 직접).
2. `cd 툴파시스템/chatapp && fly apps create tulpa-chatapp-pulpilisory`로 앱 등록.
3. 볼륨 생성(SQLite 데이터 유지용): `fly volumes create chatapp_data --size 1 --region nrt -a tulpa-chatapp-pulpilisory`
4. 워커-서버 인증 토큰을 시크릿으로 등록(이 저장소 세션에서 생성해 둔 값 재사용 —
   Mac 워커 launchd plist의 `CHATAPP_WORKER_TOKEN`과 반드시 동일해야 함):
   `fly secrets set WORKER_TOKEN=<토큰값> -a tulpa-chatapp-pulpilisory`
5. **앱 전체 접속 비밀번호도 필수로 등록한다** — 아래 "접속 비밀번호(Basic 인증)" 참고.
   `fly secrets set APP_USERNAME=<아이디> APP_PASSWORD=<비밀번호> -a tulpa-chatapp-pulpilisory`
6. `fly deploy`
7. 배포된 URL(`https://tulpa-chatapp-pulpilisory.fly.dev`)이 곧 핸드폰에서 접속할 주소다.

## 접속 비밀번호 (Basic 인증) — 필수

★ 2026-08-24: 처음엔 앱이 인증 없이 완전히 공개돼 있었고, 실제로 URL을 아는
지인이 들어와서 채팅을 어지럽힌 사고가 있었다. `APP_USERNAME`/`APP_PASSWORD`
시크릿을 둘 다 설정하면 `/api/worker/*`를 제외한 모든 요청에 HTTP Basic 인증이
걸린다(브라우저가 표준 로그인 팝업을 띄운다 — 한 번 입력하면 그 브라우저에서는
계속 기억됨). 워커는 별도 `WORKER_TOKEN`으로 인증하므로 이 비밀번호와 무관하게
계속 동작한다. 비밀번호를 아는 사람에게만 공유할 것 — URL만으로는 더 이상
못 들어온다.

## 전체 채팅방 (당분간 폐쇄됨)

★ 2026-08-24: 전체 채팅방은 아무도 안 부르면 페르소나 전원이 매번 동시에
반응하는 구조라 거의 똑같은 답이 몇 개씩 쏟아지고, 서로 일면식 없어야 할
인물들이 Notion에 없는 친분·약속을 지어내는 문제가 실사용 중 확인됐다.
`fly.toml`의 `GROUP_ROOM_ENABLED = "false"`로 방 목록에서 숨기고 새 메시지도
거부하는 중 — 1:1 방은 전혀 영향 없다. 재개하려면 그룹 대화 로직(예: 매번
전원 응답 대신 관련 있는 인물만 반응하게, 서로 모르는 인물끼리는 그 사실을
인지하게)을 먼저 고친 뒤 `"true"`로 바꾸고 재배포한다.

## Mac 워커를 항상 켜두기 (launchd)

`shift_alarm.py`와 같은 방식으로 LaunchAgent(`~/Library/LaunchAgents/com.tulpachat.worker.plist`)가
이미 등록돼 있다 — 재부팅해도 자동으로 뜨고, 크래시하면 launchd가 다시 살린다
(`KeepAlive.SuccessfulExit=false`). 로그는 `~/Library/Logs/tulpachat_worker.{out,err}.log`.
코드를 고친 뒤에는 `launchctl kickstart -k gui/$(id -u)/com.tulpachat.worker`로
재시작해야 반영된다(shift_alarm과 동일한 패턴).
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

1. 핸드폰 브라우저로 `https://<app이름>.fly.dev` 접속하면 카카오톡처럼 **방 목록**이
   먼저 뜬다 — "전체 채팅방"(모든 페르소나가 같이 있음) + 페르소나별 1:1 방.
2. 방을 눌러 들어가서 메시지를 보낸다.
   - **전체 채팅방**: 아무도 지목 안 하면 방에 있는 페르소나 전원이 한 번씩
     응답. `@이름`으로 특정 인물만 부를 수도 있다.
   - **1:1 방**: 방 자체가 그 인물이므로 `@` 없이 보내도 항상 그 사람만 응답.
3. 페르소나 프로필을 Notion에서 고치면, 워커가 5분 주기로 다시 읽어와 반영한다
   (`PERSONA_SYNC_INTERVAL_SECONDS`).
4. **대화 내용은 10분 주기로 자동으로 Notion에 반영된다** — 어떤 방에서든
   (전체 채팅방이든 1:1이든) 한 인물이 등장한 새 메시지가 4개 이상 쌓이면,
   워커가 그 구간을 AI로 짧게 요약해서 그 인물 페이지의 "함께 만든 이야기"
   섹션에 날짜와 함께 추가한다(`STORY_SYNC_INTERVAL_SECONDS`,
   `STORY_SYNC_MIN_NEW_MESSAGES`). 잡담만 있었으면 기록하지 않는다.

## 로드맵 / 알려진 제약

- **페르소나끼리 자동으로 서로 계속 이어 대화하지는 않는다** — 사용자 메시지 1건당
  대상 페르소나가 한 번씩만 응답한다. 진짜 "페르소나끼리 무한히 대화 이어가기"를
  만들려면 폭주 방지(최대 턴 수, 종료 조건)를 먼저 설계해야 한다.
- 여러 페르소나가 동시에 응답 대상이면 워커가 순차 처리한다(폴링 루프가
  한 번에 하나씩 가져옴) — 응답이 조금씩 늦게 순서대로 뜬다.
- Notion 이야기 자동 기록은 요약 하나당 AI 호출 1번이 추가로 든다(워커가 하는
  일이라 여기도 API 키 없이 CLI 재사용). 대화가 아주 활발하면 10분마다 인물
  수만큼 추가 호출이 생길 수 있다는 점 감안.
