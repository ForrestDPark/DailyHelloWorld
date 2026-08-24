# CLAUDE.md

이 저장소에서 작업하는 Claude Code 세션을 위한 안내다.

## 저장소 성격

개인 모노레포. 매일 다른 언어로 hello world를 치는 학습 기록부터 실제로 운영 중인
자동화 프로젝트까지 섞여 있다. 프로젝트별 세부 명세는 각 폴더의 `README.md`
(일부는 `AGENTS.md`)가 정본이며, 이 파일은 그것들을 대체하지 않는다.

## 운영 중인 주요 프로젝트

- [일본어 자막 추출](일본어자막추출/README.md)
- [일본어 구절 공부 파이프라인](일본어공부/README.md)
- [손자병법 구절 해석 파이프라인](손자병법/README.md)
- [이직시스템 — 사람인 채용공고 수집기](이직시스템/README.md)
- [경진대회시스템 — 출전·제출·포트폴리오 파이프라인](경진대회시스템/README.md)
- [shift_alarm — 근무 알림 메뉴바 앱 + iOS 위젯](shift_alarm/README.md)
- [툴파시스템 — 페르소나 동반자(기록·대화, 데이터는 Notion이 정본)](툴파시스템/README.md)

각 프로젝트를 건드리기 전에 해당 README부터 읽는다.

## git 관련 주의

- git sparse checkout이 걸려 있어 `git status`에 무관한 파일이 대량으로
  modified/untracked로 뜰 수 있다. 실제로 수정한 파일만 골라서 `git add`한다.
- 커밋 메시지·PR 설명 등은 한국어 존댓말로 쓴다.

## `.claude/agents/`

- `sunzi-content-writer` — 손자병법 구절 본문(원문·주석·역사 사례·현대 적용) 작성 전용
  Opus 에이전트. 전략지형도 이미지 작업은 하지 않고, `손자병법/README.md`를 유일한
  작업 명세로 삼는다.
- `jp-subtitle-study-writer` — 일본어자막추출 원문 한 편을 7섹션(상황·핵심 대화·문법·
  어휘·말투·Whisper 교정·복습)으로 분석하는 Opus 에이전트. 자막 추출·EPUB 빌드는 하지 않는다.
- `jobs-analyst` — 이직시스템 공고 분석 + `candidate_profile.json` 기반 맞춤 포트폴리오·
  자소서 초안 작성 Opus 에이전트. 크롤러 코드 변경은 하지 않는다.
- `career-pipeline-dev` — 이직시스템 파이프라인 코드(`job_collector.py`·`contest_collector.py`·
  `company_profile.py`·`ai_exec.py`·`career_profile_pipeline.py`) 수정 전용 에이전트. 분석
  콘텐츠 작성은 하지 않는다(그건 `jobs-analyst`/`contest-scout` 영역).
- `contest-scout` — 경진대회시스템 신규 대회 발굴·평가·기록 에이전트. 직무 연관성·포트폴리오
  가치·완주 가능성·주최자 신뢰도를 함께 채점한다.
- `shift-alarm-dev` — `shift_alarm.py`/`ShiftAlarmWidget.js` 기능 수정 전용 에이전트.
  AppKit 메인 스레드 규칙, launchd stdout 버퍼링, iCloudSync 경쟁 상태 등 과거에 실제
  크래시로 확인된 함정을 알고 있다.
- `release-sync` — 이직시스템·경진대회시스템·손자병법 등에서 공통으로 쓰는 "검증 → 커밋·푸시 →
  Notion 갱신 → session_journal 기록" 마무리 절차를 실행하는 공용 에이전트. 기능 구현은 하지 않는다.
