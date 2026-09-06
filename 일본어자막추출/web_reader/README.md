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
- Apple Books 전용 Media Overlay 자동 넘김은 브라우저에서 재현하지 않는다. EPUB에
  들어 있는 일반 오디오 요소는 재생할 수 있고, 원본 EPUB 내려받기도 제공한다.
