# 이직시스템 — 사람인·워크넷 채용공고 수집기

사람인·워크넷(고용24) 공식 채용정보 API로 공고를 모으고, 필요하면 사람인·알바몬 공개 검색결과 페이지 크롤링(로그인/CAPTCHA 우회 없음)을 보조 수단으로 병행해 SQLite에 누적한다. 동일한 공고는 `(source, source_id)` 기준으로 중복 저장하지 않고 마감일·조건만 갱신한다. 공고의 기술 키워드를 자동 태그하고, 내가 정한 포함·제외 키워드로 0~100점의 적합도를 계산한다.

## 운영 원칙 — 공고를 학습 커리큘럼으로 쓴다

채용공고를 보고 `지금의 나와 안 맞는다`는 이유로 바로 버리지 않는다. 지원자격은 기업이 원하는 능력을 공개한 문서이므로, 반복되는 요구사항을 공부·포트폴리오·면접 준비의 기준으로 삼는다.

- **지금 지원 가능:** 핵심 요건의 60~70% 정도를 설명하고 증명할 수 있다.
- **1~3개월 준비 후 지원:** 부족한 기술이 명확하고 학습과 프로젝트로 보완할 수 있다.
- **장기 목표:** 특정 업무의 연차·대규모 운영 경험처럼 단기간에 대체하기 어려운 조건이 있다.

이 시스템의 목표는 `공고 수집 → 요구 기술 분해 → 반복 빈도 집계 → 내 기술과 비교 → 학습 과제 생성 → 포트폴리오로 증명 → 지원`이다.

## 후보자 프로필·맞춤 포트폴리오/자소서 파이프라인

두 로컬 원본 폴더(`/Users/forrestdpark/Desktop/이전 자소서`, `/Users/forrestdpark/Desktop/자소서`)의 이력서·자소서·포트폴리오를 재사용 가능한 근거 저장소로 정리했다(★ 2026-08-09).

- `career_profile_pipeline.py scan`: DOCX·PPTX·PDF·HWP·Pages를 스캔해 `data/career_profile/`에 비공개 텍스트 코퍼스와 출처 인덱스를 만든다. 주민등록표·신분증·통장·건강보험·성적증명 등은 파일명 규칙으로 자동 제외한다.
- `candidate_profile.json`: 다른 Codex·Claude 세션과 공고 분석기가 읽는 Git 공유용 비식별 구조화 프로필. 연락처·주소·생년월일·주민번호·계좌·건강정보는 넣지 않는다.
- `CAREER_PROFILE.md`: 사람이 빠르게 읽는 경력·프로젝트·자소서 서사 요약과 맞춤 작성 규칙.
- `job_collector.py`: 공고 분석 시 공유 프로필을 자동으로 읽어 기존 회사·공고 분석 뒤에 **맞춤 포트폴리오 구성**과 **맞춤 자기소개서 초안**을 함께 만든다. 근거 없는 경력·숫자는 만들지 않고 `verification_queue` 항목은 확인 필요로 표시한다.
- 원본 문서와 `data/career_profile/` 추출본은 Git에 올리지 않는다. 새 문서가 생기면 `scan` → 근거 검토 → `candidate_profile.json`·`CAREER_PROFILE.md` 갱신 순서로 관리한다.

```bash
python3 career_profile_pipeline.py scan
python3 career_profile_pipeline.py validate
```

상세 프로필과 프로젝트 우선순위는 [CAREER_PROFILE.md](CAREER_PROFILE.md)를 참고한다.

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
python3 job_collector.py analyze <source_id> [--source "사람인(크롤링)"]
python3 job_collector.py analyze-top --category career    # 커리어(사람인·워크넷) 1위, ★ 2026-08-08
python3 job_collector.py analyze-top --category parttime  # 알바(알바몬·알바천국) 1위, ★ 2026-08-08
```

- `collect`: 검색어를 차례로 조회하고 `data/jobs.db`에 저장한다.
- `list`: 적합도가 높은 공고부터 터미널에 보여준다(각 줄의 URL 옆에 붙은 값이 아니라 별도로 source_id를 확인하려면 `export`나 DB를 직접 조회).
- `export`: 전체 공고를 엑셀에서도 열 수 있는 `exports/jobs.csv`로 내보낸다.
- **`analyze` (★ 2026-08-07 추가, "운영 원칙" 실전 도구)**: 공고 하나의 요구사항·우대사항을 AI로 읽어서 ①요약 ②이 회사가 실제로 뭘 만들려는지 추론 ③그걸 뒷받침할 연습 프로젝트 1~2개 ④(★ 2026-08-07 추가) **1인 사업자로 이 회사를 직접 창업한다면**의 사업계획서 항목화(사업 아이템·목표 고객·수익 모델·최소 실행 조직·초기 필요 역량·시장 진입 전략·차별점) — 지원자 관점뿐 아니라 창업자 관점에서도 같은 공고를 뜯어본다. `job_collector.py`의 `analyze_job()`/`fetch_job_detail_text()`, AI 호출은 `ai_exec.py`(일본어자막추출과 동일한 codex→claude 폴백 패턴, 파일 복사해서 이 폴더에도 둠).
  - 같은 `source_id`가 여러 소스에 있으면 `--source`로 지정해야 한다(예: `"사람인"` API와 `"사람인(크롤링)"`은 ID 체계가 다를 수 있어 별도 소스로 저장됨).
  - **사람인 URL 함정(실사용 중 발견)**: DB에 저장된 사람인 URL(`zf_user/jobs/relay/view?...`)은 본문이 JS로 나중에 로드돼 curl로는 사이트 메뉴/푸터만 잡히고 실제 요구사항은 0글자다. 구버전 URL `zf_user/jobs/view?rec_idx={source_id}`는 서버 렌더링이라 본문이 그대로 잡히므로, 사람인 소스일 때는 자동으로 이 URL을 대신 쓴다.
  - **이미지형 공고 감지**: 위 대체 URL을 써도 "자격요건/우대사항/주요업무" 같은 표준 섹션 제목이 하나도 안 잡히면(회사가 요구사항을 이미지로만 올린 경우 등) AI를 부르지 않고 경고만 띄운다 — 본문 없이 AI에 넘기면 근거 없는 추측을 만들어내기 때문.

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
## 3-2-1. 알바천국 사이트맵 기반 수집 (`enable_alba_crawl`, ★ 2026-08-08 추가)

`enable_alba_crawl: true`일 때만 동작하는 보조 수집원. 검색결과 페이지(`/search/`, `/Job/List` 등 여러 URL 패턴 시도)는 정상 UA·Referer를 붙여도 매번 "일시적인 장애가 발생하였습니다"라는 안내 페이지(HTTP 200)만 돌아와 결국 실제 검색 API를 못 찾았다 — 알바몬과 달리 SSR로 데이터가 박혀 있지 않은 클라이언트 렌더링(SPA) 방식으로 보인다.

- **검색 대신 sitemap.xml을 쓴다.** `https://www.alba.co.kr/sitemap.xml`(인덱스) → 가장 최근 `lastmod`인 하위 사이트맵 하나 선택 → 그 안의 `https://www.alba.co.kr/job/Detail?adid={id}` 형태 상세 URL들을 최대 100개(`ALBA_CRAWL_MAX_RESULTS`) 순서대로 모은다(`fetch_alba_sitemap_urls`). 사이트맵 하나에 실측 5,758건이 들어있어 전체를 다 가져오지 않고 앞쪽만 자른다.
- 상세 페이지(`/job/Detail?adid=...`)는 서버 렌더링이라 curl로 바로 읽히고, `og:description` 메타 태그에 `"[알바천국] 지역 / 회사명 / 공고명 / 급여"` 형식으로 이미 정리돼 있어 HTML 본문을 파싱할 필요가 없다(`fetch_alba_detail`, 실측 확인).
- **검색어 개념이 없다** — 사이트맵에서 최신 공고를 그냥 모아온 뒤, `job_collector.py`의 `score_job()`으로 로컬 키워드 점수만 매긴다(링커리어 공모전 크롤러와 같은 방식). 그래서 `collect()`의 검색어 루프 밖에서 한 번만 실행된다(`fetch_alba_crawl`, `matched_query="알바천국 최신 공고(사이트맵)"` 고정값).
- **버그(실사용 중 발견)**: 일부 공고의 `og:description`에 급여 단위를 강조하려는 `&lt;span class=&#39;detail-pay__unit&#39;&gt;원&lt;/span&gt;` 같은 **이스케이프된 HTML 태그**가 그대로 섞여 나온다(사이트 쪽 버그로 보임). `html.unescape()`로 먼저 엔티티를 풀어야 실제 `<span>` 형태가 되므로, 태그 제거 정규식을 **unescape 다음에** 적용해야 한다 — 순서를 반대로 했다가 태그가 안 지워지는 버그를 실제로 겪었다.
- 상세 페이지 하나당 요청 1건이라(최대 100건) 만료·삭제된 공고 하나가 전체 배치를 죽이지 않게, 개별 조회 실패는 `RuntimeError`를 잡아 건너뛴다(`fetch_alba_crawl`).
- 요청 사이 `ALBA_CRAWL_DELAY_SECONDS`(1초) 딜레이.

## 3-3. 공모전·경진대회 수집 (`contest_collector.py`, ★ 2026-08-07 추가, ★ 2026-08-08 다중 소스로 확장)

채용공고와 별개로 공모전·경진대회를 같은 철학("공고를 학습 커리큘럼으로 쓴다")으로 다룬다 — 실력 검증 기회이자, 참가하지 않더라도 "이 대회가 뭘 원하는지" 분석 자체가 학습 재료다. `data/contests.db`에 별도 저장하며, `job_collector.py`와 완전히 분리된 파일이다(도메인이 달라 스키마도 다름).

```bash
python3 contest_collector.py collect        # 링커리어(최대 100건) + 전국민 AI 경진대회(전체) + 콘테스트코리아(최대 60건) 수집
python3 contest_collector.py list --limit 20
python3 contest_collector.py analyze-top --category ai       # AI경진대회(정부) 1위, ★ 2026-08-08
python3 contest_collector.py analyze-top --category general  # 링커리어+콘테스트코리아 1위, ★ 2026-08-08
```

- **링커리어(linkareer.com)만 우선 구현**했다(2026-08-07, 사용자 요청으로 여러 후보 사이트 중 하나씩 순차 추가하기로 함). `/list/contest` 페이지가 Next.js SSR이라 `__NEXT_DATA__`의 `activityItems`(제목·URL)와 `__APOLLO_STATE__`의 `Activity:{id}`(주최·마감일 등 정규화 캐시)를 조합해서 읽는다 — 알바몬 크롤러와 같은 패턴.
- **`?keyword=` 검색 파라미터는 서버 렌더링에 반영되지 않는다** — 항상 "최신 20건"만 내려준다(확인됨). 그래서 검색 대신 `?page=1~5`로 여러 페이지(최대 100건)를 모은 뒤, `job_collector.py`의 `score_job()`과 동일한 방식(`config.json`의 include/exclude_keywords 재사용)으로 로컬 점수를 매긴다.
- 공모전 상세 페이지(`https://linkareer.com/activity/{id}`)는 서버 렌더링이라 curl로 본문(참여대상/시상규모/접수기간/상세내용)이 바로 잡힌다.
- AI 분석은 5개 항목: ①참여자격/공모분야/평가기준 요약 ②이 대회가 검증하려는 역량 추론 ③참가 시 접근 전략 ④**경진대회 주제 맞춤 출품 아이디어 3개** ⑤1인 사업자 관점 상품화(이 문제를 사업 아이템으로 본다면). 아이디어마다 문제·주제 적합성, 핵심 기능, 1인 MVP, 심사 차별점을 적고 최우선 추천 하나를 표시하므로 Notion에서 바로 출품 후보를 고를 수 있다(★ 2026-08-09 추가).
- Notion 발행은 `job_collector.py`와 같은 "🎴 이직시스템" 페이지 밑, 페이지 하나만 매일 갱신하는 방식을 그대로 재사용(`_notion_publish`가 두 파일에 거의 동일하게 존재 — 도메인별 파일 분리 원칙을 지키려고 공용 모듈로 합치지 않음).
- **아직 미구현(후속 예정)**: 데이콘(dacon.io, 순수 클라이언트 렌더링이라 실제 API 엔드포인트 발견 필요), allforyoung.com, 위비티(wevity.com), 씽굿(thinkcontest.com), 해외 플랫폼(Devpost 등).

### 3-3-1. 전국민 AI 경진대회(aichallenge4all.or.kr, 정부 주관) (★ 2026-08-08 추가)

`collect()`가 링커리어 다음으로 이어서 수집하는 두 번째 소스. 목록 페이지(`/competitions/all`)는 Next.js **App Router**라 `__NEXT_DATA__`가 없고 React Server Component 스트리밍 페이로드(`self.__next_f.push(...)`)로 데이터가 오는데, 이건 파싱하기 까다로운 비표준 포맷이다 — 대신 브라우저가 실제로 호출하는 REST API `https://aichallenge4all.or.kr/api/competitions`를 그대로 쓴다(인증 불필요, 페이지네이션 없이 전체 목록 한 번에 반환, 실측 33건).

- `fetch_aichallenge4all()`이 `badgeStatus == "closed"`(종료)만 걸러내고 나머지(모집중/참가중/상시/준비중)는 전부 후보로 남긴다 — 정부 주관 큐레이션 플랫폼이라 33건 전체가 이미 AI 관련이라서 링커리어처럼 페이지를 여러 장 넘길 필요가 없다.
- 응모기간(`applyPeriod`)에 `<br/>` 같은 HTML 태그가 그대로 섞여 있는 경우가 있어(실측 확인) 태그를 `" / "`로 치환해 여러 시즌 정보를 한 줄로 정리한다.
- `organizer`는 API에 별도 필드가 없어 `"전국민 AI 경진대회(정부 주관)"` 고정값을 쓴다. `url`은 `detailUrl` → `externalUrl` → 없으면 `aichallenge4all.or.kr/competitions/{slug}` 순으로 폴백.

### 3-3-2. 콘테스트코리아(contestkorea.com) (★ 2026-08-08 추가)

`collect()`의 세 번째 소스. 옛날 방식 PHP 게시판 사이트라 링커리어·전국민AI경진대회와 달리 JSON이 전혀 없고, 사람인 크롤러(3-1)와 같은 순수 정규식 HTML 블록 분리 방식으로 파싱한다.

- 목록 URL: `https://www.contestkorea.com/sub/list.php?int_gbn=1&Txt_bcode={카테고리코드}&page={N}`. 카테고리는 "학문・과학・IT"(`Txt_bcode=030310001`)만 우선 수집 — 다른 카테고리(문학・문예, 아이디어・건축・창업 등)도 각자 다른 `bcode`를 쓰는데, 필요해지면 `CONTESTKOREA_CATEGORY_BCODE`를 추가하면 된다. 페이지당 12건, 최대 5페이지(60건)까지.
- `list_style_2` 클래스 안 `<li>` 블록마다 `<div class="title">`(제목·상세 URL), `<ul class="host">`(주최), `<div class="date">`(접수기간)가 있어 각각 정규식으로 추출(`_CK_TITLE_RE`/`_CK_HOST_RE`/`_CK_DEADLINE_RE`, `fetch_contestkorea_page`/`parse_contestkorea_block`).
- 상세 URL은 `view.php?...&str_no={id}` 형태이며 `str_no`를 `source_id`로 쓴다. 상세 페이지도 완전히 서버 렌더링이라 curl로 참가대상/접수기간/시상내역/참가비용이 그대로 잡힌다(실측 확인).
- **알려진 한계**: `deadline`이 "06.05~08.04"처럼 연도 없는 자유 텍스트라 마감 여부를 코드로 걸러내지 못한다. 실제로 이미 마감된 공고가 analyze-top에 뽑힌 적이 있는데(2026-08-08 실측), 다행히 AI가 원문의 접수 마감 시각을 보고 "현재 날짜 기준으로는 종료된 공모전"이라고 스스로 짚어줬다 — 링커리어(정확한 ISO 날짜)·전국민AI경진대회(`badgeStatus`)처럼 구조화된 마감 필터가 없다는 점을 인지하고 쓸 것.

## 3-4. 기업 경영 분석 (`company_profile.py`, ★ 2026-08-07 추가)

회사 하나를 지정하면 DART(전자공시) 재무정보 + 이직시스템에 이미 수집된 채용공고·공모전 + 회사 홈페이지 텍스트를 모아, 손자병법 해석에서 역사적 실증사례를 드는 것처럼 근거를 명시하며 경영 서사를 분석한다. "이 회사는 어떻게 경영해왔는가·누가 운영하는가·업계에서 어떤 위치인가"를 판단하는 게 목적.

```bash
python3 company_profile.py analyze "(주)회사명" --url "https://회사홈페이지/about"
```

- **DART API 키(★ 2026-08-08 키체인으로 전환)**: `export DART_API_KEY=...`도 여전히 되지만, `_dart_api_key()`가 환경변수 우선·없으면 macOS 키체인 `dart_api_key` 항목을 읽는다 — `security add-generic-password -a $USER -s dart_api_key -w "<키>"`. shift_alarm이 launchd로 떠서 셸 프로필의 export를 못 보는 문제를 `jp_subtitle_notion_token`과 같은 방식으로 해결(3-1 참고).
- **DART OpenAPI**: `corpCode.xml`(zip 안 XML, 전체 공시대상 기업의 회사명→corp_code 매핑, 30일 로컬 캐시) → `company.json`(기업개황 — 대표자·주소·**홈페이지(`hm_url`)** 등) → `fnlttSinglAcntAll.json`(최근 3개년 재무제표, 연결 우선/별도 폴백)에서 매출액·영업이익·당기순이익·자산총계만 추출. `DART_API_KEY`가 없으면 이 단계 전체를 건너뛰고 나머지 정보만으로 분석(비상장 소규모 기업은 키가 있어도 애초에 공시가 없어 똑같이 건너뜀 — 정상 상황). `hm_url`이 없는 회사는 DART가 빈 문자열 대신 `"-"` 같은 자리표시자를 주기도 해서(실측: 에스컴퍼니, 2026-08-08), URL처럼 안 생겼으면(`.` 없음) 버리게 했다.
- 회사명 매칭은 정확히 일치 우선, 안 되면 "(주)"/"주식회사" 등을 뗀 이름으로 느슨하게 재시도.
- 홈페이지 URL은 선택이지만 있으면 서사 품질이 좋아진다. 단, React/Vue 등 순수 클라이언트 렌더링 페이지는 curl로 빈 텍스트만 잡힌다(예: nculture.co.kr — "You need to enable JavaScript" 46자만 수신됨, 확인됨).
- AI 분석은 6개 항목: ①기업 개황 ②재무 상태 해석(없으면 "DART 미등록"으로 명시) ③채용·공모전 이력에서 보이는 경영 방향 ④종합 서사 ⑤**병법적 해석**(★ 사용자 요청, 2026-08-07) — 정보 노출을 감추는 방식(궤도)·자원 배분(허실)·유리한 형세를 먼저 만드는지(形·勢)·때를 기다리는지(진퇴) 등을 손자병법 개념으로 재해석하되, 근거 없이 손자병법을 인용만 하지 않도록 "이 부분은 병법적으로 해석할 근거가 부족하다"고 명시하는 경우를 허용 ⑥관점별 시사점(구직자/파트너/투자자).
- Notion 발행은 회사명별로 별도 상태 파일(`data/company_profiles/<회사명>.json`)에 `page_id`를 저장해서, 같은 회사를 다시 분석하면 새 페이지 대신 기존 페이지를 갱신한다(다른 기능들과 같은 "페이지 하나만 계속 갱신" 원칙).

### 3-4-1. 오늘의 추천 공고 선정에도 연동(★ 2026-08-07, 2026-08-08 페이지 구성 개편)

기존엔 키워드 점수(`score_job()`)로만 1위를 골라서, 재무·경영 이력을 전혀 알 수 없는 무명 소기업이 뽑히는 경우가 많았다. `job_collector.py`의 `_rank_candidates_by_analyzability()`가 후보를 DART 등록 여부로 재정렬해서(등록 기업 우선), 실제로 심층 분석이 가능한 회사가 우선 선택되게 했다. `DART_API_KEY`가 없으면 이 재정렬은 건너뛰고 기존 점수 순서 그대로 쓴다.

선정된 회사에 대해 `analyze_top_job()`이 `company_profile.py`의 함수(`build_company_prompt`/`_notion_publish` 등)를 직접 import해서 기업 경영 분석 페이지(병법적 해석 포함)도 별도 하위 페이지로 같이 만들고, 공고 분석 페이지 meta 줄에 그 링크를 남긴다 — 공고 하나를 보다가 "이 회사는 어떤 회사인가"까지 한 번에 확인할 수 있게(★ 2026-08-08: 공고 페이지 안에 통째로 합칠지 검토했으나, "경영 분석만 따로 훑어보기"가 더 낫다는 판단으로 별도 페이지+링크 방식을 유지하기로 함).

**★ 2026-08-08 공고 페이지 상단 구성 개편** — "제일 궁금한 건 이 회사가 지금 뭘 하려는지 추론인데 그게 맨 위에 안 뜬다, 홈페이지·재무 정보도 상단에 있으면 좋겠다"는 피드백으로:
- `build_analysis_prompt()`의 4개 항목 순서를 요약→추론→프로젝트→사업계획서에서 **추론→요약→프로젝트→사업계획서**로 바꿨다 — AI가 그 순서 그대로 답하므로 Notion 페이지에도 "① 이 회사가 지금 만들려는/겪고 있는 것 추론"이 본문 맨 위에 온다.
- meta 블록에 DART `hm_url`(회사 홈페이지)을 추가하고, 재무 요약은 `점수 | 소스 | URL` 슬래시 텍스트 한 줄 대신 **Notion 표 블록**(`_dart_financial_table_block()`)으로 만든다 — 연도별(최근 3개년) 행 × 매출액/영업이익/당기순이익/자산총계/부채총계/자본총계 열. 원 단위 큰 숫자(`77002948664`)는 `_format_krw()`가 억/조 단위(`770억원`)로 바꿔서 보여준다("숫자 그대로는 성의 없다"는 피드백).

**★ 2026-08-08 최상위 "🎴 이직시스템" 페이지에 히스토리 토글 누적** — "카테고리별 하위 페이지"는 여전히 "페이지 하나만 매일 갱신"이라 어제 추천은 사라진다. 이걸로는 과거 기록이 안 남는다는 지적으로, `_append_history_toggle()`이 매번 발행 후 최상위 페이지(`NOTION_JOBSYSTEM_PAGE_ID`)에 그날 결과를 **접힌 토글**로 추가한다 — 토글 제목은 `[날짜][카테고리] 제목` 형식(예: `[2026-08-08][career] 🎯 [커리어 공고] ...`)이고, 하위 페이지에 실제로 발행한 것과 같은 블록을 토글 안에 그대로 넣는다(자체 완결된 스냅샷이라 다음날 하위 페이지가 덮어써져도 이 토글 내용은 그대로 남는다). 같은 날 같은 카테고리로 재실행하면(수동 재실행·테스트 등) 새 토글을 추가하지 않고 제목이 일치하는 기존 토글의 내용만 교체해서 중복 누적을 막는다. `contest_collector.py`의 `analyze_top_contest()`에도 동일한 함수(파일별로 중복 구현, 기존 관례)로 똑같이 적용됨.
- **Notion 페이지 블록 삭제 페이지네이션 버그 발견·수정(★ 2026-08-08)**: 하위 페이지를 매일 갱신할 때 기존 블록을 지우는 로직(`_notion_publish`)이 `page_size=100` 딱 한 페이지만 조회해서 지웠는데, AI 분석 하나가 100블록을 넘기는 경우가 흔해(사업계획서까지 포함하면 특히) 100개 넘는 나머지가 안 지워지고 다음 날 내용이 그 뒤에 계속 쌓이는 버그가 실측으로 발견됐다((주)크라우드웍스 페이지에 전날 다믈파워반도체 내용이 섞여 있었음). `job_collector.py`/`contest_collector.py`/`company_profile.py` 세 파일 모두 "결과가 빌 때까지 첫 페이지를 반복 조회해서 지운다" 방식으로 고쳤다(삭제 중 커서가 밀리는 걸 피하려고 `next_cursor`를 안 쓰고 매번 첫 페이지부터 다시 조회).

## 4. 다음 확장

- macOS에서 매일 1회 자동 실행
- 노션 `이직시스템`의 공고 DB로 신규·변경 공고만 동기화
- 이력서와 공고를 비교해 `즉시 지원 / 준비 후 지원 / 제외`로 분류
- 마감 3일 전 macOS 알림
- 알바천국(alba.co.kr) 실제 검색 API 경로 파악 후 크롤러 추가

공식 API(사람인·워크넷)를 우선 사용하고, 로그인·CAPTCHA 우회 없는 공개 검색결과 페이지 크롤링(사람인·알바몬, 잡코리아는 robots.txt로 제외)을 보조 수단으로 병행한다. 로그인 우회, CAPTCHA 우회, 비공개 정보 수집은 여전히 하지 않는다.
