# 이직시스템 — 사람인·워크넷 채용공고 수집기

사람인·워크넷(고용24) 공식 채용정보 API로 공고를 모으고, 필요하면 사람인·알바몬 공개 검색결과 페이지 크롤링(로그인/CAPTCHA 우회 없음)을 보조 수단으로 병행해 SQLite에 누적한다. 동일한 공고는 `(source, source_id)` 기준으로 중복 저장하지 않고 마감일·조건만 갱신한다. 공고의 기술 키워드를 자동 태그하고, 내가 정한 포함·제외 키워드로 0~100점의 적합도를 계산한다.

## 운영 원칙 — 공고를 학습 커리큘럼으로 쓴다

채용공고를 보고 `지금의 나와 안 맞는다`는 이유로 바로 버리지 않는다. 지원자격은 기업이 원하는 능력을 공개한 문서이므로, 반복되는 요구사항을 공부·포트폴리오·면접 준비의 기준으로 삼는다.

- **지금 지원 가능:** 핵심 요건의 60~70% 정도를 설명하고 증명할 수 있다.
- **1~3개월 준비 후 지원:** 부족한 기술이 명확하고 학습과 프로젝트로 보완할 수 있다.
- **장기 목표:** 특정 업무의 연차·대규모 운영 경험처럼 단기간에 대체하기 어려운 조건이 있다.

이 시스템의 목표는 `공고 수집 → 요구 기술 분해 → 반복 빈도 집계 → 내 기술과 비교 → 학습 과제 생성 → 포트폴리오로 증명 → 지원`이다.

## 현재 구축 상태

- 사람인 API 이용 신청 완료, **사용 승인 대기 중**(2026-08-03 신청, 거절 확정 아님)
- **워크넷(고용24) API 연동 완료(★ 2026-08-05)**: `openapi.work.go.kr`가 `work24.go.kr`로 통합됨에 따라 `WORK24_ACCESS_KEY` 기반으로 별도 수집원 추가. 사람인과 별개로 `source="워크넷"`으로 저장
- **사람인 공개 검색결과 크롤링 구현 완료(★ 2026-08-05)**: API 승인 대기 중에도 수집이 끊기지 않도록, 로그인·CAPTCHA 우회 없이 `zf_user/search/recruit` 검색결과 페이지를 표준 라이브러리(`re`)만으로 파싱하는 보조 수집원 추가. 기본은 꺼져 있고 `config.json`의 `"enable_saramin_crawl": true`로 옵트인. `source="사람인(크롤링)"`으로 API 수집분과 구분 저장(같은 공고라도 ID 체계가 달라 정확한 병합 보장이 안 되므로 소스를 분리함)
- 검색어별 수집, SQLite 저장, `(source, source_id)` 기준 중복 제거·갱신 구현 완료
- 기술 태그·포함/제외 키워드 적합도·CSV 내보내기 구현 완료
- 사람인 API 승인 후 실데이터 수집을 검증하고, 지원 가능성 분류·부족 역량 분석·Notion DB 동기화를 연결할 예정

## Codex·Git·Notion 동기화 규칙

이직시스템 작업에서 재사용할 원칙이나 기능 변경이 나오면 같은 작업 내에서 다음을 처리한다.

1. 코드와 이 README를 함께 수정한다.
2. `verify_before_sync.sh`로 테스트·문법·비밀값 포함 여부를 확인한다.
3. 이직시스템 관련 파일만 커밋해 `main`에 푸시한다.
4. [Notion 이직시스템](https://app.notion.com/p/3b132a1eae80805dad0ed4f2cae02709)의 진행 상태·운영 원칙·다음 행동을 같이 갱신한다.

자세한 Codex 실행 원칙은 `AGENTS.md`에 있다. 이 동기화는 **Codex가 이직시스템 작업을 수행할 때마다** 적용된다. Codex 세션이 없는 시간에 대화를 감시하는 백그라운드 프로세스는 아니다.

## 1. 최초 설정

1. [사람인 채용정보 API](https://oapi.saramin.co.kr/guide/job-search)에서 Access Key를 발급받는다. 워크넷도 쓰려면 [고용24 오픈API](https://www.work24.go.kr)에서 인증키를 발급받는다(舊 openapi.work.go.kr가 work24.go.kr로 통합됨).
2. 설정 파일을 만든다.

   ```bash
   cd /Users/forrestdpark/Desktop/PDG/DailyHelloWorld_/이직시스템
   cp config.example.json config.json
   ```

3. `config.json`의 `queries`, `include_keywords`, `exclude_keywords`를 내 조건에 맞게 수정한다. `config.json`과 수집 DB는 Git에 올라가지 않는다.
4. API 키는 현재 터미널에만 설정한다. 둘 다 없으면(사람인 승인 대기 등) `enable_saramin_crawl`이 켜져 있을 때만 수집이 진행된다.

   ```bash
   export SARAMIN_ACCESS_KEY='발급받은_키'
   export WORK24_ACCESS_KEY='발급받은_키'
   ```

5. (선택) API 키 없이도 수집을 계속하고 싶으면 `config.json`에 `"enable_saramin_crawl": true`를 추가한다 — 사람인 공개 검색결과 페이지를 크롤링해서 `source="사람인(크롤링)"`으로 저장한다(3-1 참조).

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

`queries`의 검색어 하나당 각 API(사람인/워크넷)를 한 번씩 호출한다. 예제처럼 검색어가 3개면 수집 한 번에 사람인 3회 + 워크넷 3회(둘 다 키가 있을 때)다. `results_per_query`는 호출 횟수가 아니라 검색어별로 받을 공고 수다(사람인 API 최대 110건/워크넷 최대 100건/크롤링 최대 100건으로 각각 상한).

## 3-1. 사람인 공개 검색결과 크롤링 (보조 수집원, ★ 2026-08-05)

`enable_saramin_crawl: true`일 때만 동작하는 보조 수집원. **로그인·CAPTCHA 우회 없이** `https://www.saramin.co.kr/zf_user/search/recruit` 검색결과 페이지(공개, robots.txt 허용 범위)를 가져와 표준 라이브러리 `re`만으로 `item_recruit` 공고 블록을 잘라 파싱한다(`job_collector.py`의 `fetch_saramin_crawl_query`/`parse_saramin_crawl_block`).

- 요청 사이 `SARAMIN_CRAWL_DELAY_SECONDS`(1.5초) 딜레이를 넣어 과도한 요청을 피한다.
- 결과는 `source="사람인(크롤링)"`으로 저장한다. API 결과(`source="사람인"`)와 ID 체계가 다를 수 있어 같은 공고라도 자동 병합을 보장할 수 없으므로 소스를 분리했다 — 같은 공고가 두 줄로 보일 수 있다는 뜻.
- **잡코리아는 크롤링하지 않는다.** `jobkorea.co.kr/robots.txt`가 `/Search/?stext=`를 일반 크롤러 전체(`User-agent: *`)에 Disallow하고, ClaudeBot 등 AI 크롤러는 사이트 전체를 차단하고 있어 이 방침을 존중한다(2026-08-05 확인).
- 필드 파싱은 최선 노력(best-effort) 방식이다 — 사람인이 마크업을 바꾸면 일부 필드가 빈 값으로 떨어질 수 있고, 그때는 정규식(`_SARAMIN_*_RE`)을 실제 HTML에 맞춰 다시 조정해야 한다.

## 3-2. 알바몬 공개 검색결과 크롤링 (단기계약직·알바, ★ 2026-08-07)

`enable_albamon_crawl: true`일 때만 동작하는 보조 수집원. 알바몬 검색결과 페이지(`https://www.albamon.com/total-search?keyword=...`)는 Next.js SSR이라 `<script id="__NEXT_DATA__">` 안에 공고 목록이 이미 구조화된 JSON(react-query 캐시)으로 들어있어, HTML 마크업 파싱 없이 표준 라이브러리(`json`)만으로 그대로 읽는다(`job_collector.py`의 `fetch_albamon_crawl_query`/`parse_albamon_job`).

- **실제 검색 URL은 `/jobs?keyword=`가 아니라 `/total-search?keyword=`다** — `/jobs`는 robots.txt에 ClaudeBot 등 AI 크롤러에 `Allow`로 명시돼 있지만 그 자체가 검색 결과 페이지 경로는 아니었다(처음 시도한 `/jobs?keyword=`는 HTTP 404). `sitemap.xml → total-search/sitemap.xml`에서 실제 URL 패턴을 확인했다.
- `queries[].queryKey[0] == "SEARCH_RECRUIT_LIST"`인 react-query 캐시 항목의 `state.data.base.normal.collection` 배열이 공고 목록이다. 페이지당 20건, `&page=N`으로 페이지네이션.
- 공고 상세 URL은 `https://www.albamon.com/jobs/detail/{recruitNo}`.
- 결과는 `source="알바몬(크롤링)"`으로 저장한다. 급여는 `payType.description`(예: "시급"/"월급") + `pay`를 합쳐서 쓴다 — `payType`에는 `value`에 내부 코드("A000")가 들어있어 그쪽을 쓰면 사람이 못 읽는 값이 나온다.
- 요청 사이 `ALBAMON_CRAWL_DELAY_SECONDS`(1.5초) 딜레이. `queries`는 사람인/워크넷과 동일한 목록을 그대로 재사용한다 — 반도체/TCAD 같은 검색어는 알바몬에서 결과가 0건이어도 그냥 넘어가고, 서빙·물류·판매 계열 공고는 자연히 걸린다.
- **알바천국(alba.co.kr)은 아직 미구현이다.** robots.txt(`User-agent: *`)는 `/search/`를 명시적으로 허용하지만, 실제로 `/search/?keyword=`에 요청하면 정상 UA·Referer를 붙여도 "일시적인 장애가 발생하였습니다"라는 안내 페이지(HTTP 200)만 돌아온다 — 알바몬처럼 SSR로 데이터가 박혀 있지 않고 클라이언트 렌더링(SPA) 방식이라 실제 검색 API 경로를 아직 못 찾았다. 나중에 브라우저 개발자도구로 실제 API 호출을 확인해서 추가해야 한다.

## 4. 다음 확장

- macOS에서 매일 1회 자동 실행
- 노션 `이직시스템`의 공고 DB로 신규·변경 공고만 동기화
- 이력서와 공고를 비교해 `즉시 지원 / 준비 후 지원 / 제외`로 분류
- 마감 3일 전 macOS 알림
- 알바천국(alba.co.kr) 실제 검색 API 경로 파악 후 크롤러 추가

공식 API(사람인·워크넷)를 우선 사용하고, 로그인·CAPTCHA 우회 없는 공개 검색결과 페이지 크롤링(사람인·알바몬, 잡코리아는 robots.txt로 제외)을 보조 수단으로 병행한다. 로그인 우회, CAPTCHA 우회, 비공개 정보 수집은 여전히 하지 않는다.
