# GEMINI.md

이 저장소에서 작업하는 Gemini 세션을 위한 안내다. Claude 세션은 `CLAUDE.md`를 쓰고, 일부
서브프로젝트는 Codex용 `AGENTS.md`를 따로 두고 있다(`이직시스템/AGENTS.md`,
`경진대회시스템/AGENTS.md`) — 이 파일은 그 둘과 같은 역할을 Gemini에게 제공하기 위한 것이며,
내용은 최대한 `CLAUDE.md`와 맞춰져 있다. 셋 중 하나가 바뀌면 가능하면 나머지도 같이 갱신한다.

## 저장소 성격

개인 모노레포. 매일 다른 언어로 hello world를 치는 학습 기록부터 실제로 운영 중인
자동화 프로젝트까지 섞여 있다. 프로젝트별 세부 명세는 각 폴더의 `README.md`
(일부는 `AGENTS.md`)가 정본이며, 이 파일은 그것들을 대체하지 않는다. **작업을 시작하기 전에
반드시 해당 프로젝트의 README부터 읽는다** — 이 파일에 적힌 요약이 아니라 README가 최신 상태의
정본이다.

## 운영 중인 주요 프로젝트

- [일본어 자막 추출](일본어자막추출/README.md)
- [일본어 구절 공부 파이프라인](일본어공부/README.md)
- [손자병법 구절 해석 파이프라인](손자병법/README.md)
- [이직시스템 — 사람인 채용공고 수집기](이직시스템/README.md) (Codex 작업 규칙: `이직시스템/AGENTS.md`)
- [경진대회시스템 — 출전·제출·포트폴리오 파이프라인](경진대회시스템/README.md) (Codex 작업 규칙: `경진대회시스템/AGENTS.md`)
- [shift_alarm — 근무 알림 메뉴바 앱 + iOS 위젯](shift_alarm/README.md)
- [툴파챗 — 페르소나 동반자(기록·대화, 데이터는 Notion이 정본)](툴파챗/README.md)

## 세션 시작 시 가장 먼저 할 일

```bash
cd "/Users/forrestdpark/Desktop/PDG/DailyHelloWorld_"
python3 session_journal/session_journal.py check
```
Claude·Codex·Gemini가 공용으로 쓰는 작업 일지("클로드코덱스 이력정리" Notion 페이지, 이름은
만들어진 시점 그대로지만 지금은 모든 에이전트가 공유)에 마지막으로 기록된 커밋과 실제 로컬
Git 상태를 대조해서, 다른 세션(사람·Claude·Codex 어느 쪽이든)이 최근에 뭘 했는지, dirty한
파일이 남아있는지 한 번에 보여준다. 자세한 내용·제약은 `session_journal/README.md` 참고.

## 작업을 마쳤을 때 — 공용 인계장에 기록

```bash
python3 session_journal/session_journal.py add \
  --agent Gemini \
  --status 완료 \
  --title "짧은 제목" \
  --request "사용자가 뭘 요청했는지" \
  --changes "실제로 뭘 바꿨는지 (왜 바뀌었는지 중심으로)" \
  --verification "뭘로 검증했는지" \
  --risks "남은 일·위험(선택)" \
  --next-prompt "다음 세션이 이어받을 때 쓸 프롬프트(선택)"
```
Git 커밋 해시·변경 파일·푸시 여부는 커밋 직후 호출하면 자동으로 붙는다. 아직 커밋 전인
진행 중 작업은 `--status 진행 중`과 `--no-git`. 처음 쓰는 필드 조합이 걱정되면 먼저
`--dry-run`으로 결과만 확인한다.

## 이 저장소에서 지켜야 할 공통 규칙

- **대화는 항상 한국어 존댓말로.** 반말은 쓰지 않는다.
- **git**: sparse checkout이 걸려 있어 `git status`에 무관한 파일이 대량으로 modified/untracked로
  뜰 수 있다. 실제로 수정한 파일만 골라서 `git add <경로>`한다 (`-A`/`.` 금지). 커밋 메시지는
  한국어 존댓말로 쓴다. **커밋 후 push는 사용자에게 물어보지 않고 바로 진행한다** — 단
  push 전에 `git fetch && git log HEAD..origin/main --oneline`으로 원격에 새 커밋이 있는지
  확인하고, 있으면 fast-forward 가능한 선에서 반영 후 push한다. force-push 등 파괴적 작업은
  이 자동 진행 대상이 아니며 항상 먼저 확인받는다.
- **README를 정본으로 유지**: 프로젝트 관련 기능·규칙을 바꾸면, 같은 턴(또는 같은 커밋)에
  해당 프로젝트의 `README.md`도 함께 최신화한다. README는 "다른 기기·다른 세션·다른 에이전트가
  이전 대화 맥락 없이도 바로 이어서 작업할 수 있게" 만든 문서라는 게 이 저장소 전체의 설계
  원칙이다 (`손자병법/README.md`, `shift_alarm/README.md`가 대표적인 예).
- **shift_alarm.py를 고쳤다면**, 세션 안의 관련 작업이 다 끝난 뒤 `shift_alarm/README.md`
  1번 항목에 적힌 명령으로 메뉴바 앱을 재시작한다 (rumps 앱이라 hot-reload가 없어서, 재시작해야
  실제로 수정사항이 반영된 걸 확인할 수 있다).
- **민감정보**: API 키, 개인 이력서, 연락처·주민번호·계좌 등은 Git에 커밋하지도, 외부 프롬프트에
  통째로 넣지도 않는다 (`이직시스템/AGENTS.md`에 더 자세한 기준이 있다).
- 로그인·CAPTCHA·접근 제한 우회, robots.txt로 막힌 사이트 크롤링은 하지 않는다.

## `.claude/agents/`

Claude Code 전용 서브에이전트 정의라 Gemini가 직접 호출할 수는 없지만, 이 저장소가 프로젝트별
작업을 어떻게 역할 분담해왔는지 보여주는 참고 자료로는 유용하다 (예: 손자병법 본문 작성 전용
에이전트, shift_alarm 코드 수정 전용 에이전트 등). `CLAUDE.md`에 전체 목록이 있다.
