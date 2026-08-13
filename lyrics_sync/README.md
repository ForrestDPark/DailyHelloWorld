# lyrics_sync — mp3 가사를 자막처럼(.lrc) 만들기

아이폰 nPlayer로 mp3를 들을 때 가사를 자막처럼 같이 보고 싶다는 요청으로
추가했다(2026-08-13). mp3와 같은 폴더에 같은 이름의 `.lrc`(동기화 가사) 파일이
있으면 nPlayer가 자동으로 자막처럼 띄워준다.

## 순서 (사용자 지정)

1. **1번: [lrclib.net](https://lrclib.net)** — 무료·API 키 불필요·공개 동기화
   가사 DB에서 먼저 찾는다. mp3의 ID3 태그(아티스트·제목·길이)로 조회한다.
2. **2번: whisper-cli 자체 전사** — 1번에서 못 찾은 곡만, 로컬 Whisper(whisper.cpp,
   `일본어자막추출`에서 쓰는 것과 같은 도구)로 직접 전사해서 `.lrc`를 만든다.
   whisper-cli의 `-olrc` 옵션이 타임스탬프 포함 LRC를 바로 만들어준다.

이미 `.lrc`가 있는 곡은 건너뛴다(`--overwrite`로 강제 재생성 가능).

## 사용법

```bash
# 기본 대상: ~/Desktop/BlogImage/좋아요플레이 (알람에서 재생하는 감상용 플레이리스트)
python3 lyrics_sync.py

# 다른 폴더
python3 lyrics_sync.py "/path/to/mp3/folder"

# 테스트로 5곡만
python3 lyrics_sync.py --limit 5

# 이미 있는 .lrc도 다시 생성
python3 lyrics_sync.py --overwrite
```

## lrclib.net 조회 방식

- ID3 태그의 artist/title은 yt-dlp가 채워넣은 채널명·영상 제목 그대로라 잡음이
  많다(`(Official Video)`, `M/V`, `(Official Lyric Video)` 등) — `clean_title()`이
  이런 패턴을 정규식으로 제거하고, 제목이 "Artist - Title"처럼 아티스트를
  중복 포함하면 앞부분을 잘라낸다.
- 먼저 `/api/get`(아티스트+제목+길이로 정확 매칭)을 시도하고, 실패하면
  `/api/search`로 검색해서 `syncedLyrics`가 있는 결과 중 실제 재생 길이와
  가장 가까운 것을 고른다 — 단, ±10초를 넘게 차이나면 다른 곡으로 오매칭된
  것으로 보고 버리고 whisper로 넘어간다.

## whisper-cli 전사 방식 — VAD는 절대 켜지 않는다

`일본어자막추출` 파이프라인은 (대사가 있는) 영상에 Silero VAD를 켜서 무음
구간을 건너뛰는데, **노래에 VAD를 그대로 가져다 쓰면 안 된다**는 걸 실측으로
확인했다(2026-08-13): Silero VAD는 대화체 음성 검출용으로 학습돼 있어서,
반주가 깔린 보컬(가창)을 "음성 없음"으로 오판하는 경우가 있다. 실제로 애니메
엔딩곡 하나를 VAD 켜고 돌렸더니 `whisper_vad_segments_from_probs: Final speech
segments after filtering: 0`으로 나오면서 결과 `.lrc`가 완전히 빈 채로
나왔다 — VAD를 끄니 정상적으로 가사가 나왔다. 그래서 `lyrics_sync.py`는 VAD를
전혀 쓰지 않는다.

모델은 `일본어자막추출`과 같은 `ggml-medium.bin`(이미 설치돼 있음), 언어는
`auto`(라이브러리에 한국어·영어·일본어가 섞여 있어서). 순수 반주곡(가사 없는
피아노 커버 등)은 whisper가 `[MUSIC]` 같은 태그만 출력하는데, 이건 정상
동작이다(지어낸 가사를 만들지 않는 것).

## 알려진 한계

- lrclib은 무료 커뮤니티 DB라 마이너한 곡·커버·리믹스는 없을 수 있다 — 그런
  경우 자동으로 whisper 전사로 넘어간다.
- whisper 전사는 사람이 직접 만든 가사 싱크만큼 완벽하지 않다(특히 랩처럼
  빠른 구간, 여러 명이 동시에 부르는 구간).
- 순수 반주곡이나 랩·보컬이 거의 없는 곡은 whisper가 가사를 거의 못 뽑아낼 수
  있다 — 오탐(없는 가사를 지어내는 것)보다는 적게 뽑는 쪽으로 치우쳐 있다.
