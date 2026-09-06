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

## 3-2-2. Gmail 채용 뉴스레터 수집 (`ingest-email`, ★ 2026-08-14 추가)

`collect`의 검색어/사이트맵 루프와 무관하게, shift_alarm이 Gmail 새 메일을 5분마다 확인하다가 사람인(`saramin.co.kr`) 발신 메일을 보면 본문을 통째로 넘겨 호출하는 **push 방식** 수집원이다(다른 소스는 전부 이쪽에서 pull하는 방식과 반대).

- `python3 job_collector.py ingest-email`은 stdin으로 `{"sender":..., "subject":..., "body":...}` JSON을 받는다(본문이 수만 자라 argv로 넘기기엔 부적합). shift_alarm 쪽 호출부는 `shift_alarm/README.md` 18번 항목 참고.
- `extract_job_postings_from_email()`이 사람인 뉴스레터의 클릭트래킹 링크(`api-mail.saramin.co.kr/mail-bridge?url=...`)에서 실제 채용공고 URL과 `rec_idx`를 정규식으로 복원한다. AI에게는 URL 자체를 베끼게 하지 않고 "후보 링크 순번 목록 + 본문 텍스트"만 주고 회사명·제목·마감일이 몇 번 링크와 짝인지 고르게 한다 — URL의 긴 쿼리스트링을 AI가 그대로 옮겨 적게 하면 오타가 날 위험이 있어서다.
- `rec_idx`가 숫자가 아닌 후보(광고 배너 등 href가 깨진 경우, 실사용 중 확인)는 자동으로 걸러진다. 잡코리아 링크는 robots.txt 크롤링 금지 원칙(운영 원칙 참고)에 따라 항상 제외한다.
- 추출된 공고는 `source="사람인"`, `source_id=rec_idx`로 `upsert_jobs()`된다 — API/크롤링으로 이미 수집된 같은 공고와 `(source, source_id)` 키가 같으면 그대로 병합되고, `JOB_SOURCE_CATEGORY`가 이미 `"사람인": "career"`라 새 카테고리 등록도 필요 없다. `fetch_job_detail_text()`도 `source_id`만 있으면 자동으로 크롤링 가능한 구버전 URL로 치환하므로, 이후 점수화·AI 분석·Notion 발행은 기존 사람인 공고와 완전히 동일한 경로를 탄다.
- **지금은 사람인만 지원한다** — 다른 발신자(점핏 등)는 `extract_job_postings_from_email()`이 빈 리스트를 반환해 조용히 건너뛴다. 확장하려면 발신자별로 실제 링크를 안전하게 복원할 방법(클릭트래킹 우회, robots.txt 확인)을 먼저 검증해야 한다.
- **검증(2026-08-14)**: 실제 사람인 뉴스레터(회사 20건)로 별도 테스트 DB에 end-to-end 실행 — mail-bridge 링크 21개 중 숫자 `rec_idx` 19개 추출, AI가 19건 전부 회사명·제목·마감일을 메일 원문과 정확히 일치시켜 매칭, 그중 1건은 `fetch_job_detail_text()` 상세 크롤링도 정상 동작(5356자, `_content_available()` True)함을 확인.
- Notion에 즉시 발행하지 않는다 — DB 반영까지만 하고, 하루 1번 도는 `analyze-top --category career`가 점수 1위일 때 자연스럽게 골라 분석·발행한다(메일마다 즉시 AI 호출하면 빈도가 너무 잦아짐).

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
- AI 분석은 **경진대회 주제 맞춤 출품 아이디어 3개**를 1번에 배치하고, 이어서 참여자격·공모분야·평가기준 요약, 검증 역량 추론, 참가 전략, 1인 사업자 관점 상품화를 작성한다. 아이디어마다 문제·주제 적합성, 핵심 기능, 1인 MVP, 심사 차별점을 적고 최우선 추천 하나를 표시하므로 Notion에서 바로 출품 후보를 고를 수 있다(★ 2026-08-09 순서 개선).
- **AI 도구 로그 발행 방지(★ 2026-08-10)**: Codex 실패 후 Claude 폴백이 최종 답변 대신 `Bash: Check memory index...` 같은 내부 도구 실행 로그만 종료 코드 0으로 반환한 사례가 있었다. `ai_exec.run_ai_exec()`의 선택적 응답 검증기와 `_valid_contest_analysis()`가 최소 길이·필수 5개 섹션·도구 흔적 부재를 모두 확인하며, 검증에 실패한 출력은 Notion에 발행하지 않고 다음 엔진/후보로 넘긴다.
- `analyze-top`은 `_is_deadline_expired()`로 ISO 날짜와 연도 없는 `MM.DD~MM.DD` 접수기간을 현재 날짜에 맞춰 해석해 마감 공모전을 제외한다. `_looks_student_only()`는 대학생·대학원생 전용 대회를, `_looks_organization_only()`는 참가 대상이 ALIO 공시 공공기관 등 기관으로 제한된 대회를 제외한다(★ 2026-08-10). 기관이 주최한다는 이유만으로 제외하지 않고 참가 대상·자격 문맥에 제한이 명시된 경우만 거른다. 날짜·자격이 불명확하면 임의로 탈락시키지 않고 후보로 남긴다.
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
- **연도 없는 마감일 처리(★ 2026-08-09)**: `deadline`이 `06.05~08.04`처럼 연도 없는 자유 텍스트여도 `_parse_deadline_end()`가 종료 월·일을 현재 연도에 대입해 마감 여부를 판정한다. 연말·연초 경계처럼 확정할 수 없는 입력은 보수적으로 후보에 남긴다.
- **주최사 홈페이지 상세 정보 추가 수집(★ 2026-09-03)**: "경진대회 크롤링할때 주최사 홈페이지 링크가 있는 경우에는 주최사 홈페이지로 가서 관련정보도 수집했으면 좋겠어" 요청. 콘테스트코리아 상세 페이지엔 요약만 있고 실제 상세 요강(참여대상·평가기준·신청방법 등)은 주최사 자체 사이트에 따로 있는 경우가 있다(실측 사례: "K-인공지능 제조데이터 분석 경진대회"의 실제 상세가 kamp-ai.kr에 있었음). `fetch_contest_detail_text()`가 페이지의 "홈페이지" 표 행에서 주최사 링크를 찾아(`_extract_organizer_homepage_link()`) 있으면 그 페이지도 같이 받아 붙인다.
  - 실측 함정: 실제 링크가 `<a href="javascript:void(0)">`(클릭 추적용)로 가려져 있었고, 진짜 URL은 그 위에 **주석 처리된** `<!-- <a href="..."> -->` 안에 그대로 남아 있었다 — `href="..."` 패턴만 찾으면 주석 여부와 무관하게 잡히므로 그대로 활용했다.
  - 실측: 이 방식으로 kamp-ai.kr 페이지에서 신청기간·대회방식(2개 트랙)·평가기준·시상내역까지 실제로 끌어오는 것을 확인(콘테스트코리아 페이지만으로는 없던 정보). 이 표 행이 없는 출처(링커리어·전국민AI경진대회)에서는 조용히 빈 문자열을 돌려주고 원래 텍스트만 쓴다.

## 3-4. 기업 경영 분석 (`company_profile.py`, ★ 2026-08-07 추가)

회사 하나를 지정하면 DART(전자공시) 재무정보 + 이직시스템에 이미 수집된 채용공고·공모전 + 회사 홈페이지 텍스트를 모아, 손자병법 해석에서 역사적 실증사례를 드는 것처럼 근거를 명시하며 경영 서사를 분석한다. "이 회사는 어떻게 경영해왔는가·누가 운영하는가·업계에서 어떤 위치인가"를 판단하는 게 목적.

```bash
python3 company_profile.py analyze "(주)회사명" --url "https://회사홈페이지/about"
```

- **DART API 키(★ 2026-08-08 키체인으로 전환)**: `export DART_API_KEY=...`도 여전히 되지만, `_dart_api_key()`가 환경변수 우선·없으면 macOS 키체인 `dart_api_key` 항목을 읽는다 — `security add-generic-password -a $USER -s dart_api_key -w "<키>"`. shift_alarm이 launchd로 떠서 셸 프로필의 export를 못 보는 문제를 `jp_subtitle_notion_token`과 같은 방식으로 해결(3-1 참고).
- **DART OpenAPI**: `corpCode.xml`(zip 안 XML, 전체 공시대상 기업의 회사명→corp_code 매핑, 30일 로컬 캐시) → `company.json`(기업개황 — 대표자·주소·**홈페이지(`hm_url`)** 등) → `fnlttSinglAcntAll.json`(최근 3개년 재무제표, 연결 우선/별도 폴백)에서 매출액·영업이익·당기순이익·자산총계만 추출. `DART_API_KEY`가 없으면 이 단계 전체를 건너뛰고 나머지 정보만으로 분석(비상장 소규모 기업은 키가 있어도 애초에 공시가 없어 똑같이 건너뜀 — 정상 상황). `hm_url`이 없는 회사는 DART가 빈 문자열 대신 `"-"` 같은 자리표시자를 주기도 해서(실측: 에스컴퍼니, 2026-08-08), URL처럼 안 생겼으면(`.` 없음) 버리게 했다.
- **공식 근거 링크·업종 해석(★ 2026-08-09)**: `dart_filing_search_url()`과 `dart_company_overview_url()`이 DART 공시검색·기업개황 링크를 만들고, `ksic_industry_hint()`가 DART `induty_code` 앞 2자리로 KSIC 중분류 업종을 설명한다. 5자리 세세분류를 추측하지 않고 통계청 분류표 확인 링크를 안내한다.
- **회사 뉴스(★ 2026-08-09)**: `fetch_company_news()`가 네이버 뉴스 검색 결과의 현재 `sds-comps-*` 마크업을 읽는다. 요청에는 User-Agent뿐 아니라 `Accept-Language`와 `Referer`가 모두 필요하다. 코드가 직접 검증할 수 없는 크레딧잡·잡플래닛·홈택스 링크는 제공하지 않는다.
- **추천 점수의 뉴스 원문 공개(★ 2026-08-13)**: `회사 정보 신뢰도` 또는 `사업자·회사 정보`에 `뉴스 N건`이라고 표시하면, 정밀 채점 때 실제로 수집한 `news_items`를 버리지 않고 바로 아래에 `뉴스 1~N: [기사 제목](원문 URL)`으로 모두 나열한다. 건수와 링크 목록은 반드시 같은 수집 결과에서 나오므로 이후 재검색 결과나 다른 회사 뉴스가 섞이지 않는다.
- **공식 홈페이지 핵심 메뉴 수집(★ 2026-08-13)**: DART 등에 회사 홈페이지가 있으면 대표 화면만 읽지 않고 같은 공식 도메인 안의 `채용공고·인사제도·복리후생·기업소개·경영방침·제품소개·연구/기술` 링크를 최대 10개까지 제한적으로 따라간다. 추천공고 상단의 `회사 홈페이지` 바로 아래에 각 세부 페이지의 링크와 수집 본문 요약을 실제 하위 항목으로 표시하고, 같은 원문을 기업 경영 분석 프롬프트에도 넣는다. 외부 도메인이나 로그인·CAPTCHA 페이지는 따라가지 않는다.
- **문장별 괄호 출처 의무화(★ 2026-08-09)**: 별도의 `출처 지도`나 `참고 링크` 모음을 만들지 않는다. 기업 홈페이지·DART·뉴스에서 가져온 사실이나 판단은 해당 문장 바로 뒤에 `(출처: [자료명](원문 URL))` 형식으로 붙인다. 내부거래·승계·계열분리·소송·과로 등 기사 기반 판단도 같은 방식으로 기사 제목을 직접 연결한다. 링크가 없는 구체적 사실은 쓰지 않고 `정보 부족`으로 남긴다.
- 회사명 매칭은 정확히 일치 우선, 안 되면 "(주)"/"주식회사" 등을 뗀 이름으로 느슨하게 재시도.
- 홈페이지 URL은 선택이지만 있으면 서사 품질이 좋아진다. 단, React/Vue 등 순수 클라이언트 렌더링 페이지는 curl로 빈 텍스트만 잡힌다(예: nculture.co.kr — "You need to enable JavaScript" 46자만 수신됨, 확인됨).
- AI 분석은 7개 항목: ①기업 개황 ②재무 상태 해석 ③채용·공모전 이력에서 보이는 경영 방향 ④종합 서사 ⑤병법적 해석 ⑥**세무·회계·노무 관점** ⑦관점별 시사점. 병법 항목은 形·勢·詭道를 근거와 함께 묶고, 진퇴는 행군편의 구체적 신호쌍이 있을 때만 판단하며, 허실은 기업이 사람을 어떻게 다루는지의 관점으로 본다. 근거가 없으면 해당 해석을 생략한다.
- Notion 발행은 회사명별로 별도 상태 파일(`data/company_profiles/<회사명>.json`)에 `page_id`를 저장해서, 같은 회사를 다시 분석하면 새 페이지 대신 기존 페이지를 갱신한다(다른 기능들과 같은 "페이지 하나만 계속 갱신" 원칙).

### 3-4-1. 오늘의 추천 공고 선정에도 연동(★ 2026-08-07, 2026-08-08 페이지 구성 개편)

`score_job()`의 포함 키워드 +10/제외 키워드 -25는 수집 단계에서 최대 200건의 후보를 빠르게 줄이는 1차 점수일 뿐이다. 실제 일일 추천은 `score_recommendation_candidate()`가 비식별 `candidate_profile.json`과 공고 필드를 대조해 **설명 가능한 100점 점수**를 새로 계산한다(★ 2026-08-09 전면 개편).

- **커리어 100점**: 직무 핵심 적합도 30 + 내 경험·기술 근거 25 + 지원 현실성 15 + 성장·학습 가치 10 + 회사 정보 신뢰도 10 + 최신성·마감 여유 5 + 선호조건·정보 완성도 5. 설정의 제외 키워드는 건당 -15점(최대 -30점) 감점한다.
- **알바 100점**: 업무 적합도 30 + 근무시간 명확성 20 + 위치 적합도 15 + 급여 투명성 15 + 내 기술 활용도 10 + 최신성·마감 여유 5 + 사업자·회사 정보 5에서 불일치 감점을 적용한다. 알바는 DART보다 실제 근무 가능성과 조건 공개를 훨씬 크게 본다.
- **알바 추천 자격 필터(★ 2026-08-13)**: 알바는 점수 계산 전에 코딩·개발·AI·데이터·자동화·온라인 업무 근거가 있는 공고만 남긴다. 재택·원격·비대면 공고는 지역과 무관하게 허용하고, 출근형 공고는 `parttime_locations`(미설정 시 아산·천안 통근권)와 일치해야 한다. 이 자격을 통과해도 종합점수가 50점 미만이면 추천하지 않으며, 조건을 만족하는 공고가 없는 날은 낮은 품질의 매장·서빙·물류 알바로 빈자리를 채우지 않고 알바 추천 항목 자체를 표시하지 않는다. Shift Alarm도 오래된 상태 파일의 50점 미만 알바를 메뉴와 위젯에서 숨긴다.
- **당근알바 연동 보류(★ 2026-08-13 확인)**: 당근알바는 지역형 공고가 많아 좋은 보조 수집원 후보지만, 현재 `robots.txt`가 AI 에이전트의 `/kr/` 전체 접근과 일반 크롤러의 `/kr/jobs/s/` 검색 경로를 막고 있고 공개 구인공고 API도 확인되지 않았다. 로그인·접근제한을 우회하는 자동 수집기는 만들지 않는다. 당근이 공식 API나 허용된 피드를 제공하면 아산·천안 및 재택 기술형 필터를 그대로 적용해 추가한다.
- **DART는 가점이지 필터가 아니다**: DART 등록, 실제 재무 연도 수, 뉴스, 같은 회사의 관련 공고는 회사 정보 항목 안에서만 가점을 준다. DART 미등록, 재무제표 없음, API 키 없음, 일시적 조회 실패 중 어느 경우에도 후보를 제외하지 않는다.
- 선정된 Notion 페이지에는 `추천 점수 / 1차 수집 점수`를 분리해서 표시하고, 각 평가 항목의 획득점수·최대점수·근거와 감점 이유를 줄별로 공개한다.

선정된 회사에 대해 `analyze_top_job()`이 `company_profile.py`의 함수(`build_company_prompt`/`_notion_publish` 등)를 직접 import해서 기업 경영 분석 페이지(병법적 해석 포함)도 별도 하위 페이지로 같이 만들고, 공고 분석 페이지 meta 줄에 그 링크를 남긴다 — 공고 하나를 보다가 "이 회사는 어떤 회사인가"까지 한 번에 확인할 수 있게(★ 2026-08-08: 공고 페이지 안에 통째로 합칠지 검토했으나, "경영 분석만 따로 훑어보기"가 더 낫다는 판단으로 별도 페이지+링크 방식을 유지하기로 함).

**★ 2026-08-08 공고 페이지 상단 구성 개편** — "제일 궁금한 건 이 회사가 지금 뭘 하려는지 추론인데 그게 맨 위에 안 뜬다, 홈페이지·재무 정보도 상단에 있으면 좋겠다"는 피드백으로:
- `build_analysis_prompt()`의 4개 항목 순서를 요약→추론→프로젝트→사업계획서에서 **추론→요약→프로젝트→사업계획서**로 바꿨다 — AI가 그 순서 그대로 답하므로 Notion 페이지에도 "① 이 회사가 지금 만들려는/겪고 있는 것 추론"이 본문 맨 위에 온다.
- meta 블록에 DART `hm_url`(회사 홈페이지)을 추가하고, 재무 요약은 `점수 | 소스 | URL` 슬래시 텍스트 한 줄 대신 **Notion 표 블록**(`_dart_financial_table_block()`)으로 만든다 — 연도별(최근 3개년) 행 × 매출액/영업이익/당기순이익/자산총계/부채총계/자본총계 열. 원 단위 큰 숫자(`77002948664`)는 `_format_krw()`가 억/조 단위(`770억원`)로 바꿔서 보여준다("숫자 그대로는 성의 없다"는 피드백).

**★ 2026-08-27 최상위 "🎴 이직시스템" 추천 인덱스** — 맨 위의 `📋 최근 추천 기록` 토글(`TOP_INDEX_TOGGLE_ID`)에서 `🎯 오늘의 추천 공고`, `🏆 오늘의 추천 경진대회`, `🏢 기업 경영 분석 목록`, `🗄 마감·종료 보관`을 분리한다. 0점은 정보 공백으로 추천 근거가 없다는 뜻이므로 발행하지 않는다. 공고·대회는 `source:source_id` 고유키로 중복을 합산하고 최초 추천 때 날짜가 붙은 **불변 Notion 스냅샷**을 만든다. 이후 재추천은 그 스냅샷 링크를 유지하며 횟수·최근일·최고점만 갱신한다. ISO 마감일이 지난 기록은 활성 추천에서 보관 구역으로 자동 이동한다. 기존의 한 페이지 덮어쓰기 링크만 가진 과거 항목은 원문을 복원할 수 없으므로 레거시 기록으로만 취급한다.
- **공개문 검증**: 채용·기업·경진대회 분석 모두 필수 섹션, 최소 길이와 내부 도구/에이전트 흔적 부재를 확인한 뒤에만 Notion에 발행한다. `jobs-analyst 에이전트에 위임`, `Bash`, 도구 호출 표식 같은 중간 대화는 검증 실패로 처리해 다음 엔진이나 후보로 넘긴다.
- **서비스 역할**: Career Loop는 추천·회사·준비사항·스터디를 보고 행동하는 기본 화면, Notion은 구조화된 추천/기업/지원 데이터와 깊은 기록, GitHub는 수집·점수·동기화 규칙의 원본, Shift Alarm은 알림과 Career Loop 진입점이다.
- **Notion 페이지 블록 삭제 페이지네이션 버그 발견·수정(★ 2026-08-08)**: 하위 페이지를 매일 갱신할 때 기존 블록을 지우는 로직(`_notion_publish`)이 `page_size=100` 딱 한 페이지만 조회해서 지웠는데, AI 분석 하나가 100블록을 넘기는 경우가 흔해(사업계획서까지 포함하면 특히) 100개 넘는 나머지가 안 지워지고 다음 날 내용이 그 뒤에 계속 쌓이는 버그가 실측으로 발견됐다((주)크라우드웍스 페이지에 전날 다믈파워반도체 내용이 섞여 있었음). `job_collector.py`/`contest_collector.py`/`company_profile.py` 세 파일 모두 "결과가 빌 때까지 첫 페이지를 반복 조회해서 지운다" 방식으로 고쳤다(삭제 중 커서가 밀리는 걸 피하려고 `next_cursor`를 안 쓰고 매번 첫 페이지부터 다시 조회).

## 모바일 이직 준비실 웹 대시보드 (★ 2026-09-06 추가)

툴파챗의 `나의 작업실`에서 `/career/`로 여는 관리자 전용 대시보드를 추가했다.
`web_dashboard/`의 HTML·CSS·JavaScript가 모바일 카드 화면을 구성하고, 툴파챗
서버의 `/api/career-summary`가 기존 `top_job_notion_career.json`과
`top_job_notion_parttime.json`을 읽어 전달한다.

- 공개용 추천 결과에 이미 들어 있는 회사명·공고명·점수·출처·공고/Notion 링크만
  표시하며 `candidate_profile.json`, 인증 정보, API 키는 읽거나 노출하지 않는다.
- 관리자 세션이 아니면 화면과 API 모두 403으로 막는다.
- 휴대폰에서는 한 열 카드와 홈·채팅·이직·서재 하단 도크를 제공하고, 홈 화면에
  추가할 수 있도록 `manifest.webmanifest`를 제공한다.
- 현재는 최신 추천을 확인하는 최소 화면이다. 지원 상태 편집, 일정, 준비 체크리스트는
  기존 데이터 모델과 충돌하지 않게 후속 단계에서 추가한다.

## 4. 다음 확장

- macOS에서 매일 1회 자동 실행
- 노션 `이직시스템`의 공고 DB로 신규·변경 공고만 동기화
- 이력서와 공고를 비교해 `즉시 지원 / 준비 후 지원 / 제외`로 분류
- 마감 3일 전 macOS 알림
- 알바천국(alba.co.kr) 실제 검색 API 경로 파악 후 크롤러 추가

공식 API(사람인·워크넷)를 우선 사용하고, 로그인·CAPTCHA 우회 없는 공개 검색결과 페이지 크롤링(사람인·알바몬, 잡코리아는 robots.txt로 제외)을 보조 수단으로 병행한다. 로그인 우회, CAPTCHA 우회, 비공개 정보 수집은 여전히 하지 않는다.

## 스크린샷+비전 분석 폴백 (★ 2026-08-20 추가)

정적 크롤링(`fetch_job_detail_text`)으로 본문을 못 가져오는 JS 렌더링 SPA 채용공고(점핏 등)를 위해 Playwright로 스크린샷을 찍고 `claude` CLI의 Read 도구(`--allowedTools Read --add-dir <임시폴더>`)로 이미지를 직접 읽어 텍스트를 추출하는 폴백을 추가했다(`fetch_job_detail_via_screenshot()`, `run_job_analysis()`가 `_content_available()` 실패 시 자동 재시도).

- **"표준 라이브러리만 사용" 원칙의 유일한 예외**: 정적 크롤링으로는 원천적으로 못 읽는 페이지가 실사용 중 다수 확인돼(점핏 포지션 페이지 등), 사용자가 명시적으로 Playwright 도입을 승인했다(2026-08-20). `pip install playwright && python3 -m playwright install chromium` 필요.
- 사람인 공고는 relay/view가 아니라 서버 렌더링되는 구버전 URL(`zf_user/jobs/view?rec_idx=`)로 재작성한 뒤 스크린샷을 찍는다(`_effective_job_detail_url()` — 텍스트 크롤링과 스크린샷 폴백이 같은 로직을 공유). relay/view URL로 Playwright가 접속하면 봇 탐지로 30초 타임아웃이 실측됐다.
- **한계**: 일부 사이트(실측: 특정 사람인 공고 rec_idx=54484811)는 서버 렌더링 URL로 재작성해도 Playwright(헤드리스 브라우저) 접속 자체가 봇 탐지로 타임아웃 난다 — 이 경우 폴백도 실패하고 기존과 동일하게(analyze_top_job이 다음 순위 후보로 자동 이동) 처리된다. 순수 `urllib` 요청은 통과하지만 헤드리스 브라우저는 막히는 사이트가 있다는 뜻 — 회귀는 아니고(원래도 실패하던 케이스), 점핏처럼 봇 탐지가 없는 SPA에서는 잘 작동한다(실측 확인).

## 메일 채용공고 요약 표 발행 (`publish_email_job_summary_table`, ★ 2026-08-20 추가, ★ 2026-08-22 링크 보강)

`ingest_email()`이 메일 하나에서 뽑아낸 공고 전부(점수 무관)를 점수 내림차순 표로 Notion에 발행한다. 카테고리별 1건만 보여주는 `_notion_publish()`와 달리 "이 메일에 뭐가 있었는지" 그 자체가 목적이라 별도 경로다. 반환된 URL은 shift_alarm이 메일 항목에 붙여(`_attach_mail_analysis_url`) 메뉴에서 바로 연결한다.

표 컬럼은 회사·공고·마감일·점수·준비할 점이며, 앞의 세 컬럼(회사/공고/준비할 점)에 각각 링크를 건다:

- **회사**: 회사마다(중복 제거) `_generate_company_profile_url()`로 경영 분석 페이지를 만들어 링크(실패하면 평문으로 표시, 다른 회사엔 영향 없음).
- **공고**: `_effective_job_detail_url(job.url, job.source, job.source_id)`로 원문 채용공고 URL을 건다 — 크롤링·스크린샷 폴백이 쓰는 것과 같은 재작성 로직이라, 사람인 공고는 relay/view 대신 서버 렌더링되는 구버전 URL로 열린다.
- **준비할 점**: AI가 만든 팁 문구(`_suggest_job_prep_tips`)를 그대로 URL로 쓰지 않는다 — AI가 존재하지 않는 링크를 지어낼 위험이 있어서(이 코드베이스에서 반복되는 원칙: AI가 URL을 직접 만들지 않고, 검증 가능한 방식으로만 링크를 생성한다). 대신 팁 문구로 구글 검색을 거는 URL(`https://www.google.com/search?q=...`)을 걸어 항상 유효한 링크를 보장한다.

상태 파일은 발신자+제목 해시(`data/email_summaries/<hash>.json`)별로 분리돼 있어 다른 메일을 처리해도 이전 메일의 표를 덮어쓰지 않는다.

## codex 백그라운드 호출이 "Codex 완료" macOS 알림을 계속 띄우던 문제 (★ 2026-08-22)

**증상**: codex를 직접 켜놓지 않았는데도 "Codex 완료 · {cwd} / 작업을 마쳤습니다. 다음 명령을 기다리고 있습니다." 알림이 계속 떴다. 클릭해도 볼 수 있는 세션이 없다.

**원인**: `ai_exec.py`의 `_run_one()`이 매번 `codex exec`를 서브프로세스로 부르는데, `~/.codex/config.toml`에 걸린 전역 `notify` 훅(원래 Codex Computer Use 앱의 대화형 세션용)이 스코프 구분 없이 **모든** codex 실행(이 헤드리스 1회성 호출 포함)에서 turn 종료 시마다 발동해 `osascript display notification`을 쐈다. `job_collector.py`(공고·경진대회·기업 분석)와 `일본어자막추출`의 자막 보정 파이프라인이 하루에도 수십 번씩 `codex exec`를 배경에서 호출하다 보니 알림이 끊임없이 떴다.
- 확인 경로: `~/.codex/config.toml`의 `notify = [...]` → `~/.codex/notify_turn_complete.py`가 정확히 이 문구로 `display notification`을 실행.
- 수정: 두 `ai_exec.py`(이직시스템·일본어자막추출)의 codex 커맨드에 `-c notify=[]`를 추가해 이 헤드리스 호출에서만 훅을 끈다. 전역 `~/.codex/config.toml`은 건드리지 않으므로 사용자가 터미널에서 직접 여는 대화형 codex 세션의 알림은 그대로 유지된다.
