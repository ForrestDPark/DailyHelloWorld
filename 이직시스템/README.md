# 이직시스템 — 사람인 채용공고 수집기

사람인 공식 채용정보 API로 공고를 모으고 SQLite에 누적한다. 동일한 공고는 중복 저장하지 않고 마감일·조건만 갱신한다. 공고의 기술 키워드를 자동 태그하고, 내가 정한 포함·제외 키워드로 0~100점의 적합도를 계산한다.

## 운영 원칙 — 공고를 학습 커리큘럼으로 쓴다

채용공고를 보고 `지금의 나와 안 맞는다`는 이유로 바로 버리지 않는다. 지원자격은 기업이 원하는 능력을 공개한 문서이므로, 반복되는 요구사항을 공부·포트폴리오·면접 준비의 기준으로 삼는다.

- **지금 지원 가능:** 핵심 요건의 60~70% 정도를 설명하고 증명할 수 있다.
- **1~3개월 준비 후 지원:** 부족한 기술이 명확하고 학습과 프로젝트로 보완할 수 있다.
- **장기 목표:** 특정 업무의 연차·대규모 운영 경험처럼 단기간에 대체하기 어려운 조건이 있다.

이 시스템의 목표는 `공고 수집 → 요구 기술 분해 → 반복 빈도 집계 → 내 기술과 비교 → 학습 과제 생성 → 포트폴리오로 증명 → 지원`이다.

## 현재 구축 상태

- 사람인 API 이용 신청 완료, **사용 승인 대기 중**
- 검색어별 수집, SQLite 저장, 중복 제거·갱신 구현 완료
- 기술 태그·포함/제외 키워드 적합도·CSV 내보내기 구현 완료
- API 승인 후 실데이터 수집을 검증하고, 지원 가능성 분류·부족 역량 분석·Notion DB 동기화를 연결할 예정

## Codex·Git·Notion 동기화 규칙

이직시스템 작업에서 재사용할 원칙이나 기능 변경이 나오면 같은 작업 내에서 다음을 처리한다.

1. 코드와 이 README를 함께 수정한다.
2. `verify_before_sync.sh`로 테스트·문법·비밀값 포함 여부를 확인한다.
3. 이직시스템 관련 파일만 커밋해 `main`에 푸시한다.
4. [Notion 이직시스템](https://app.notion.com/p/3b132a1eae80805dad0ed4f2cae02709)의 진행 상태·운영 원칙·다음 행동을 같이 갱신한다.

자세한 Codex 실행 원칙은 `AGENTS.md`에 있다. 이 동기화는 **Codex가 이직시스템 작업을 수행할 때마다** 적용된다. Codex 세션이 없는 시간에 대화를 감시하는 백그라운드 프로세스는 아니다.

## 1. 최초 설정

1. [사람인 채용정보 API](https://oapi.saramin.co.kr/guide/job-search)에서 Access Key를 발급받는다.
2. 설정 파일을 만든다.

   ```bash
   cd /Users/forrestdpark/Desktop/PDG/DailyHelloWorld_/이직시스템
   cp config.example.json config.json
   ```

3. `config.json`의 `queries`, `include_keywords`, `exclude_keywords`를 내 조건에 맞게 수정한다. `config.json`과 수집 DB는 Git에 올라가지 않는다.
4. API 키는 현재 터미널에만 설정한다.

   ```bash
   export SARAMIN_ACCESS_KEY='발급받은_키'
   ```

## 2. 실행

```bash
python3 job_collector.py doctor
python3 job_collector.py collect
python3 job_collector.py list --limit 30
python3 job_collector.py export
```

- `collect`: 검색어를 차례로 조회하고 `data/jobs.db`에 저장한다.
- `list`: 적합도가 높은 공고부터 터미널에 보여준다.
- `export`: 전체 공고를 엑셀에서도 열 수 있는 `exports/jobs.csv`로 내보낸다.

## 3. API 호출량

`queries`의 검색어 하나당 API를 한 번 호출한다. 예제처럼 검색어가 3개면 수집 한 번에 3회다. `results_per_query`는 호출 횟수가 아니라 검색어별로 받을 공고 수다.

## 4. 다음 확장

- macOS에서 매일 1회 자동 실행
- 노션 `이직시스템`의 공고 DB로 신규·변경 공고만 동기화
- 이력서와 공고를 비교해 `즉시 지원 / 준비 후 지원 / 제외`로 분류
- 마감 3일 전 macOS 알림

지금 단계에서는 사람인 공식 API만 사용한다. 로그인 우회, CAPTCHA 우회, 비공개 정보 수집은 하지 않는다.
