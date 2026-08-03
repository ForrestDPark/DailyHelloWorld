# 이직시스템 — 사람인 채용공고 수집기

사람인 공식 채용정보 API로 공고를 모으고 SQLite에 누적한다. 동일한 공고는 중복 저장하지 않고 마감일·조건만 갱신한다. 공고의 기술 키워드를 자동 태그하고, 내가 정한 포함·제외 키워드로 0~100점의 적합도를 계산한다.

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

