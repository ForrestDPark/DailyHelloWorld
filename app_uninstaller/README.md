# app_uninstaller — macOS 앱 완전 삭제 도구

Command.app(Philips Hue 제어 앱)을 지울 때 손으로 했던 절차(앱 찾기 → 번들 ID로
`Containers`/`Group Containers`/`Application Scripts` 등 관련 파일 찾기 → 휴지통
이동)를 재사용 가능한 CLI로 일반화했다(2026-08-13).

## 사용법

```bash
# 미리보기만(기본값 — 아무것도 안 지움)
python3 app_uninstaller.py "Command"

# 실제로 휴지통에 넣기(확인 프롬프트 있음)
python3 app_uninstaller.py "Command" --delete

# 확인 프롬프트 없이 바로
python3 app_uninstaller.py "Command" --delete --yes
```

앱 이름은 부분 일치로 찾는다(`/Applications`, `~/Applications` 우선, 없으면
Spotlight로 확장 검색). 여러 개가 일치하면 후보 목록을 보여주고 정확한 이름이나
`.app` 경로를 다시 지정하라고 안내한다.

## 무엇을 찾는가

앱 번들의 `CFBundleIdentifier`(번들 ID)와 코드사인 엔타이틀먼트의
`application-groups`를 기준으로 아래 사용자 홈 폴더 위치를 훑는다:

샌드박스 컨테이너, 그룹 컨테이너, 앱 지원 파일(Application Support), 캐시,
환경설정(Preferences), 앱 스크립트, 저장된 앱 상태, WebKit/HTTP 저장소, 쿠키,
로그, 사용자 LaunchAgent.

`/Library`(시스템 전역)나 `LaunchDaemons`처럼 관리자 권한이 필요한 위치는
**자동으로 지우지 않는다** — 발견하면 "직접 확인 필요" 목록으로만 보여준다.
sudo 없이 동작하고, 실수로 다른 사용자·시스템 전역에 영향을 주지 않기 위함이다.

## 안전장치

- **기본은 항상 dry-run**이다. `--delete`를 줘야 실제로 지운다.
- 삭제는 영구 삭제가 아니라 **macOS 휴지통으로 이동**이다(Finder의 "휴지통으로
  이동"과 동일한 AppleScript 호출). 실수해도 휴지통에서 복구할 수 있다.
- `--delete`만 주면(=`--yes` 없이) 실제로 지우기 전에 대상 목록을 보여주고
  `y/N` 확인을 받는다.

## 매칭 로직과 실측으로 발견한 버그(2026-08-13)

처음엔 "짧은 이름이 긴 문자열 안에 포함되는지"도 매칭 조건으로 넣었는데, 실제로
`ChatGPT.app`(번들 ID `com.openai.codex`)을 테스트하다가 **완전히 무관한
`~/Library/Application Support/Code`(Visual Studio Code, 779MB)까지 삭제
후보에 걸리는 사고**를 발견했다 — `"code"`가 `"...openai.codex..."`라는 훨씬
긴 문자열 안에 우연히 부분 문자열로 들어있다는 이유만으로 매칭된 것이다.

그래서 매칭 방향을 다음으로 제한했다(`_is_related()`):
- 번들 ID와 **정확히 같거나**, 점(`.`)으로 구분된 접두사로 시작하는 경우
  (`notion.id.NotionSafariExtension`처럼 — 이건 Apple의 실제 명명 규칙이라 안전)
- 그룹 컨테이너 이름이 앱 그룹 엔타이틀먼트 값과 **정확히 같은** 경우(Group
  Container는 OS가 그룹 ID와 정확히 같은 이름으로 만든다)
- 번들 ID에서 뽑은 검색어(토큰, 예: `com.huecommand.app` → `huecommand`)가
  **단어 경계**(`\b`)로 둘러싸여 나타나는 경우만 — `code`가 `codex`라는 한
  단어 중간에 부분적으로 들어있는 것은 단어 경계 매칭에 걸리지 않는다.
- 앱 이름과 폴더 이름이 정확히 같은 경우

즉, "짧은 쪽이 긴 문자열 속에 파묻혀 있는지"는 절대 보지 않는다 — 이 방향이
과탐지(false positive)의 근원이었다. 이 때문에 애매한 경우(예: `ChatGPT.app`과
번들 ID를 공유하는 것으로 보이는 별도 `Codex` CLI의 데이터 폴더)는 이제 아예
후보에서 빠질 수 있다 — 놓치는 게 무관한 걸 지우는 것보다 훨씬 안전하다는
원칙을 따른다.

## 알려진 한계

- 번들 ID 기반 매칭이라, 같은 번들 ID를 공유하는 여러 실행 파일(예: GUI 앱과
  CLI 도구가 같은 팀의 서명·번들 ID를 쓰는 경우)이 있으면 관련 있어 보여도
  일부러 놓칠 수 있다(위 참고) — 안전을 우선한 설계다.
- pkg 설치 리시트(`pkgutil --pkgs`)나 커스텀 위치에 설치된 지원 파일까지는
  다루지 않는다. 표준 `~/Library` 위치 밖의 흔적은 수동으로 확인해야 한다.
