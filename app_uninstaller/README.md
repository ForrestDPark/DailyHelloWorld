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

## Launchpad에서 아이콘으로 실행하기

이 스크립트는 원래 CLI라 `/Users/forrestdpark/Desktop/PDG/DailyHelloWorld_/app_uninstaller/`에만
있고 Launchpad에는 안 뜬다("어디 설치돼 있냐"는 질문이 나온 이유 — 이건 설치된 앱이
아니라 저장소 안의 스크립트일 뿐이었다). 더블클릭으로 쓰고 싶으면 아래로 한 번
빌드하면 된다(2026-08-13 추가):

```bash
python3 build_launchpad_app.py
```

`~/Applications/Uninstall App.app`을 만든다 — 🗑️ 이모지를 렌더링해 아이콘으로
쓴다. 더블클릭(또는 Spotlight에서 실행)하면:
1. **Applications 폴더를 직접 보고 고르는 표준 Finder 열기 대화상자**가 뜬다
   (처음엔 이름을 타이핑하는 방식이었는데, "폴더에서 눈으로 보고 고르게 해달라"는
   피드백으로 바꿨다 — `choose file ... default location (path to applications
   folder) of type {"com.apple.application-bundle"}`로 .app만 선택 가능).
2. 앱을 고르면 Terminal이 열려서 `app_uninstaller.py <선택한 앱 경로> --delete`를
   실행한다(미리보기 목록 → `y/N` 확인은 CLI가 이미 하므로 그대로 안전하게 이어짐).
   취소를 누르면 조용히 아무 일도 안 일어난다.

스크립트나 아이콘을 바꾸면 `build_launchpad_app.py`를 다시 실행해서 재빌드하면
된다(기존 앱을 지우고 새로 만든다).

### 알려진 문제 — Launchpad 아이콘 그리드에 바로 안 보일 수 있음

빌드된 앱은 **Spotlight(⌘+Space)로는 항상 바로 찾아지고 정상 실행**되지만,
Launchpad를 열어서 아이콘을 눈으로 스크롤해 찾으려 하면 한동안 안 보일 수 있다.
2026-08-13에 원인을 깊게 파봤는데:

- `mdfind`(Spotlight)와 `lsregister -f`(Launch Services 강제 등록)는 항상 성공한다.
- 하지만 Launchpad 자체의 캐시 DB(`~/Library/.../com.apple.dock.launchpad/db/db`,
  경로는 `getconf DARWIN_USER_DIR`로 확인)에는 안 들어갈 때가 있다.
- `defaults write com.apple.dock ResetLaunchPad -bool true` + `killall Dock`으로
  캐시를 강제로 다시 만들어도, `lsregister -kill`로 Launch Services 데이터베이스를
  통째로 재구성해도 고쳐지지 않았다.
- **이건 이 앱만의 문제가 아니다** — 같은 방식(osacompile)으로 예전에 만든
  `음악재생.app`, `아침루틴음악재생.app`, `유튜브에서 동영상 다운.app` 등 기존
  커스텀 앱들도 대부분 Launchpad DB에 없었다(`speakPDF.app` 하나만 예외). 즉 이
  맥에서 커스텀으로 만든 .app들이 원래부터 Launchpad 그리드에 잘 안 올라가는
  경향이 있는 것으로 보인다 — 정확한 근본 원인(코드사인 관련 추정)은 못 밝혔다.

**실용적인 해결책**: Spotlight로 실행하거나, Finder에서 `~/Applications/Uninstall
App.app`을 Dock에 직접 끌어다 놓으면 확실하게 아이콘으로 뜬다. 맥을 재시동하면
Launchpad 캐시가 완전히 다시 만들어지면서 보이는 경우도 있다.

**다른 실측 함정**: 빌드 스크립트에서 파이썬 f-string에 경로를 넣을 때 `!r`(파이썬
repr)을 쓰면 작은따옴표로 감싸지는데, AppleScript 문자열은 큰따옴표만 허용한다
— `osacompile`이 실제 오류 지점보다 앞선 줄을 가리키며 "Expected expression but
found unknown token"을 내서 원인 찾기 까다로웠다. AppleScript 소스를 파이썬으로
생성할 때는 항상 큰따옴표로 직접 감쌀 것. 또한 `plutil -insert`로 `Info.plist`를
수정한 뒤에는 반드시 `codesign --force -s -`로 다시 서명해야 한다 — 안 하면
`codesign -v`가 "invalid Info.plist (plist or signature have been modified)"로
실패한다(다만 이게 Launchpad 미표시의 원인은 아니었다 — 위 참고).

## CLI 사용법

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
