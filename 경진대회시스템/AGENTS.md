# 경진대회시스템 Codex 작업 규칙

1. 작업 전에 `README.md`와 Notion `경진대회` 페이지를 재로딩한다.
2. 대회를 수상 가능성만으로 평가하지 말고, 이직 목표 기술·포트폴리오 가치·완주 가능성을 함께 본다.
3. 신뢰할 수 있는 주최자인지, 참가 자격·규칙·저작권·상금 조건이 무엇인지 출전 전에 확인한다.
4. 자동 수집은 공식 API·RSS·공개 피드를 우선하고 로그인·CAPTCHA·접근 제한을 우회하지 않는다.
5. 작업 완료 시 `./verify_before_sync.sh` 실행 → 관련 파일만 커밋 → `main` 푸시 → Notion 현재 상태 갱신 순으로 처리한다.
6. `config.json`, DB, CSV, 개인정보·API 키는 커밋하지 않는다. 사용자의 다른 dirty worktree 변경은 섞지 않는다.

Notion: `https://app.notion.com/p/3b132a1eae80804bbbb9f7f2d867e774`
