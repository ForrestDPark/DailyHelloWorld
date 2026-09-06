# 일본어 EPUB 웹 서재

`av완성작`의 EPUB을 압축 해제하거나 복사하지 않고 브라우저에서 바로 읽는 개인용 서재다.
외부 패키지가 필요 없으며 새 EPUB은 `↻` 버튼을 누르면 즉시 목록에 나타난다.

## 실행

```bash
cd /Users/forrestdpark/Desktop/PDG/DailyHelloWorld_/일본어자막추출/web_reader
JP_WEB_READER_BASE_PATH=epub ./run_web_reader.sh
```

기본 주소는 `http://127.0.0.1:8766`이다. 외부 공개 시에는 반드시 HTTPS 역방향
프록시(현재 시스템에서는 Cloudflare Tunnel) 뒤에 두고, 비밀번호는 코드나 plist에
직접 쓰지 말고 macOS 키체인에서 환경변수로 주입한다.

환경변수:

- `JP_WEB_READER_PASSWORD`: 독립 실행할 때만 쓰는 선택 비밀번호, 설정 시 8자 이상
- `JP_WEB_READER_CHATAPP_DB`: 툴파챗 세션을 확인할 DB. 관리자 계정만 허용한다.
- `JP_WEB_READER_BASE_PATH`: 기존 도메인의 하위 경로. 운영값은 `epub`
- `JP_EPUB_LIBRARY_DIR`: 완성 EPUB 폴더. 기본값은 `~/Desktop/BlogImage/av완성작`
- `JP_WEB_READER_HOST`, `JP_WEB_READER_PORT`: 기본값 `127.0.0.1`, `8766`
- `JP_WEB_READER_STATE_DIR`: 로그인 서명 키와 읽기 위치 DB 저장 폴더
- `JP_EPUB_WEB_PUBLIC_URL`: 툴파챗 워커에도 같은 값을 설정하면 일본어 선생님이
  회차 소개와 함께 `/?book=<불투명 ID>` 바로 읽기 링크를 보낸다.

## 보안·호환성

- 모든 책·본문·표지·진행 API는 로그인 쿠키를 검사한다.
- EPUB 내부의 `../` 경로는 차단하고, XHTML은 스크립트 실행을 막은 sandbox iframe과
  CSP 안에서 표시한다.
- 읽던 위치는 서버의 `~/.japanese_epub_web/reader.db`에 저장되므로 같은 서재에
  로그인한 모바일과 PC가 공유한다.
- 낭독판 EPUB의 Media Overlay(SMIL)를 서버가 읽어 각 본문·학습카드 페이지의
  음성 구간과 연결한다. 웹 리더에서 재생/일시정지, 0.75~2배속, 페이지 자동
  넘김을 쓸 수 있으며 원본 EPUB 내려받기도 그대로 제공한다.

## 웹 읽어주기 (2026-09-06)

Apple Books에서만 동작하던 `ibooks:readaloud` 속성에 의존하지 않고, EPUB OPF의
`media-overlay`와 SMIL의 `audio`·`clipBegin`·`clipEnd`를 웹 서버가 직접 해석한다.

- 현재 페이지의 일본어 본문 또는 학습카드 음성을 EPUB에 들어 있는 순서대로 재생한다.
- 재생·일시정지·이어 듣기, 0.75/1/1.25/1.5/2배속을 지원한다.
- `자동 넘김`이 켜져 있으면 페이지의 마지막 음성 뒤 다음 페이지로 이동하며,
  음성이 없는 표지·개요 페이지에서는 정지해 사용자의 의도치 않은 건너뛰기를 막는다.
- 새 TTS를 생성하거나 외부 API를 호출하지 않고 기존 낭독판 EPUB의 M4A만 사용한다.
- 실제 서재 62권을 스캔해 대표 낭독판 8권에서 페이지별 SMIL 음성이 검출되는 것을
  확인했고, SMIL 경로·구간 파싱을 포함한 서버 테스트 7개를 통과했다.
