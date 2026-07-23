# 일본어자막추출

일본어 영상을 Whisper로 자막화 → 구글 번역(한국어) → 후리가나 표기 → 노션 기록 + 애플 메모 + 통합 자막(.srt) + EPUB 생성까지 한 번에 처리하는 파이프라인. 새 세션에서도 이 문서만 보고 바로 이어서 쓸 수 있도록 정리.

- 로컬 경로: `/Users/forrestdpark/Desktop/PDG/DailyHelloWorld_/일본어자막추출/whisper_series_stream.sh`
- 원래는 macOS 단축어(Shortcuts)로 실행하던 스크립트를 그대로 저장소에 옮긴 것. 단축어 없이 터미널에서 직접 실행하거나, shift_alarm 메뉴바 앱에서도 실행 가능(아래 참조).

## 사용법

```bash
./whisper_series_stream.sh [영상 폴더 경로]   # 생략하면 현재 폴더
```

폴더 안의 `.mp4`/`.webm`/`.mkv`/`.mov` 파일을 전부 찾아서 순서대로 처리한다. 처리 중인 진행 상황은 새 터미널 창에서 실시간으로 보여준다(스크립트 자신은 그 터미널 창을 띄우고 종료 — 실제 작업은 새 창에서 백그라운드로 계속 진행됨).

## 사전 준비 — macOS 키체인에 시크릿 등록 (★ 필수, 최초 1회)

이 스크립트는 노션 토큰과 freeimage.host API 키가 필요한데, **코드에 하드코딩하지 않고 macOS 키체인에서 읽는다** (2026-07-23, 원래 스크립트에 평문으로 박혀있던 걸 이 저장소에 올리면서 옮김 — 퍼블릭 저장소라 평문으로 올리면 그 즉시 키가 인터넷에 노출됨).

```bash
security add-generic-password -a "$USER" -s "jp_subtitle_notion_token" -w "<노션 통합(integration) 토큰>" -U
security add-generic-password -a "$USER" -s "jp_subtitle_freeimage_key" -w "<freeimage.host API 키>" -U
```

`ebook_reader.py`(shift_alarm 프로젝트)가 노션 토큰을 저장하는 것과 완전히 같은 패턴. 토큰이 없으면 스크립트가 "❌ 노션 토큰을 키체인에서 찾을 수 없습니다"를 출력하고 바로 종료한다.

## 의존성

| 도구 | 용도 | 확인 |
|---|---|---|
| **iTerm2** (`/Applications/iTerm.app`) | 실제 처리가 진행되는 새 창 (★ `imgcat` 미리보기 때문에 필수 — 아래 "iTerm 자동화 권한 문제" 참고) | `brew install --cask iterm2` |
| `ffmpeg`/`ffprobe` | 오디오 추출, 장면 캡처, 이미지/오디오 합치기 | `brew install ffmpeg` |
| `/opt/homebrew/bin/whisper-cli` (whisper.cpp) | 일본어 음성 인식 | `brew install whisper-cpp` |
| `/opt/homebrew/share/whisper-cpp/models/ggml-medium.bin` (없으면 `ggml-small.bin`로 자동 폴백) | Whisper 모델 | `whisper-cpp-download-ggml-model medium` 등 |
| `pandoc` | EPUB 생성 | `brew install pandoc` (없으면 스크립트가 자동 설치 시도) |
| `/opt/homebrew/bin/imgcat` (선택) | 터미널에 장면 스냅샷 미리보기 | `brew install imgcat` — 없어도 나머지 기능은 정상 동작 |
| `pykakasi`, `requests` (anaconda python3) | 후리가나 변환, HTTP | 스크립트가 매 실행 시 자동으로 `pip install` (quiet) |
| macOS "메모" 앱, iCloud 계정, "LanguageStudy" 폴더 | 자막을 애플 메모에도 기록 | 폴더 없으면 스크립트가 자동 생성 |
| Obsidian (선택) | 완성된 EPUB을 `~/Library/Mobile Documents/iCloud~md~obsidian/Documents/Study/`에 자동 복사 | 그 경로가 없으면 복사 단계만 건너뜀, 에러 아님 |

## 처리 흐름

1. 영상 길이가 45분(2700초) 이상이면 2편으로 분할, 아니면 통으로 처리.
2. 각 파트: ffmpeg로 오디오 추출(16kHz mono, 대역폭 필터+노멀라이즈) → whisper-cli로 일본어 자막(.srt) 생성 → 파이썬 워커가 3문장씩 묶어서:
   - 각 문장 시점의 영상 프레임을 캡처해 3장을 가로로 합친 썸네일 생성(4MB 넘으면 자동 압축)
   - 구글 번역 비공식 엔드포인트로 한국어 번역
   - `pykakasi`로 한자에 후리가나 병기 (예: `漢字(かんじ)`)
   - 노션 데이터베이스에 새 페이지(영상당 1개, 2편이면 편당 1개) 생성 후 이미지+원문/번역 블록을 계속 append
   - 애플 메모 "LanguageStudy" 폴더에 같은 제목으로 노트 생성, 원문 텍스트 누적 기록
   - 로컬 `.md` 파일에 이미지+오디오(mp3)+원문/번역을 계속 append (EPUB 재료)
3. 파트별 자막을 시간축 보정해서 영상 전체의 통합 `.srt` 생성.
4. 쌓인 `.md` 파일(들)을 pandoc으로 EPUB 변환. 표지는 첫 썸네일 이미지를 재사용, 스타일은 `epub_style.css`(일본어 크고 금색, 한국어 작고 회색).
5. 완성된 EPUB을 Obsidian Study 폴더에 자동 복사(있으면).
6. 오디오 캐시(`temp_*.wav`)와 자막 캐시(`temp_*.wav.srt`)는 재실행 시 재사용됨 — 지우면 처음부터 다시 처리.

## 알려진 문제 / 수정 이력

### ★★ EPUB 생성 실패 — `--epub-version=3` 옵션이 pandoc 3.x에서 삭제됨 (2026-07-23)

**증상**: 로그에 `⚠️ EPUB 생성 실패`만 뜨고 이유를 알 수 없음.

**원인**: 원본 스크립트가 `pandoc ... --epub-version=3 ... 2>/dev/null`로 실행했는데, `--epub-version` 옵션이 pandoc 3.x(사용자 환경: 3.9.0.2)에서 완전히 제거됐다. `pandoc: Unknown option --epub-version.`로 즉시 실패하는데, 에러 출력을 `2>/dev/null`로 버려서 진짜 원인이 안 보였다.

**수정**:
1. `--epub-version=3` 옵션 삭제. `-o *.epub`만으로 이미 EPUB3로 생성되므로 버전 지정이 애초에 불필요.
2. `2>/dev/null` 대신 `${MYTMP}/pandoc_<파일명>.log`로 stderr를 저장, 실패 시 그 로그를 바로 화면에 출력하도록 변경 — 앞으로 비슷한 문제가 생겨도 원인이 바로 보임.

재현/검증: 실패했던 `MIAA-444` 작업 폴더(`~/Desktop/BlogImage/AV/`)에서 `--epub-version=3` 뺀 명령으로 직접 재실행해서 정상적으로 46MB EPUB이 만들어지는 것 확인함(표지 이미지 관련 `Could not determine image type` 경고는 뜨지만 무해함 — 실제로는 유효한 JPEG이고 pandoc의 크기 감지 로직만 못 읽는 것, 1440x270처럼 세로로 아주 납작한 비율이라 그런 것으로 추정).

### iTerm 자동화(Automation) 권한 문제 → `.command` + `open -a iTerm` 방식으로 교체 (2026-07-23, 2026-07-24 iTerm으로 재확정)

원본 스크립트는 맨 끝에서 `tell application "iTerm" ... create window ...`로 새 창을 열었는데, 이건 macOS 자동화 권한이 필요하다. 사용자가 직접 터미널에서 실행할 땐 문제없지만, **shift_alarm 메뉴바 앱(launchd 백그라운드 프로세스)에서 호출하면 권한 팝업 자체가 안 떠서 조용히 실패한다** — shift_alarm 프로젝트의 이북리더에서 이미 겪은 것과 동일한 문제(그 프로젝트 README 8-1 참조). 그래서 실행 가능한 `.command` 파일을 만들고 `open`으로 여는 방식으로 바꿨다 — 권한이 전혀 필요 없다.

**★ 2026-07-24 정정**: 처음엔 `open -a Terminal`로 바꿨었는데, 그러면 장면 미리보기(`imgcat`)가 안 보인다는 걸 사용자가 지적함 — `imgcat`은 iTerm2 전용 인라인 이미지 이스케이프 시퀀스라 일반 Terminal.app은 못 그린다. 확인해보니 **`open -a iTerm <파일>.command`도 Terminal과 동일하게 자동화 권한 없이 스크립트를 실행해준다** — 애초에 Automation(`kTCCServiceAppleEvents`) 권한이 필요한 건 `tell application "X"` 같은 AppleEvent를 보낼 때뿐이고, `open`은 Finder에서 파일을 더블클릭하는 것과 같은 취급(Launch Services)이라 대상 앱이 Terminal이든 iTerm이든 상관없이 권한이 필요 없다. 그래서 최종적으로 `open -a iTerm`으로 되돌렸다 — 권한 문제도 없고 imgcat 미리보기도 정상 동작.

## 메뉴바(shift_alarm) 연동

`shift_alarm/README.md` 참조 — 메뉴의 `🎥 일본어 자막 추출 (폴더 선택)`을 누르면 폴더 선택 다이얼로그가 뜨고, 고른 폴더로 이 스크립트를 실행한다.
