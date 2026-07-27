# BGM 및 플레이리스트 자동 분할 파이프라인

이 폴더는 `extract_high_pitch_video.py`가 운동용 영상에 배경음을 입힐 때 쓰는 MP3 보관 폴더다. 이곳의 `.mp3` 파일을 무작위 순서로 이어붙여 운동용 영상 위에 믹스한다.

---

## 긴 플레이리스트 MP4를 무음 기준 MP3로 자동 분절

`bgm_silence_splitter.py`는 Shazam이나 곡명 인식을 사용하지 않는다. ffmpeg로 플레이리스트의 무음 구간을 단계별로 탐지하고, 최소 3분 이상 이어진 오디오를 무음 지점에서 잘라 MP3를 하나씩 생성한다. 무음이 전혀 없어도 한 조각이 6분을 넘지 않게 강제 상한을 둔다.

`ffmpeg`가 없다면:

```bash
brew install ffmpeg
```

### 기본 실행

```bash
cd /Users/forrestdpark/Desktop/PDG/DailyHelloWorld_/일본어자막추출

/opt/anaconda3/bin/python3 bgm_silence_splitter.py \
  "/Users/forrestdpark/Desktop/BlogImage/BGM_DIR/플레이리스트.mp4" \
  --output-dir "/Users/forrestdpark/Desktop/BlogImage/BGM_DIR/분절기록" \
  --audio-output-dir "/Users/forrestdpark/Desktop/BlogImage/BGM_DIR" \
  --trash-source
```

원본 옆에 `<원본명>_tracks/` 폴더를 만들고 다음을 저장한다.

```text
플레이리스트 분절1.mp3
플레이리스트 분절2.mp3
...
.silence_split_state.json
```

`--trash-source`를 지정하면 모든 MP3 생성과 기록 저장이 성공한 뒤에만 원본 MP4를 macOS 휴지통으로 옮긴다. 중간에 실패하거나 사용자가 창을 닫으면 원본은 보존된다.

### 정확도 조절

```bash
# 무음 기준을 더 느슨하게 조절
/opt/anaconda3/bin/python3 bgm_silence_splitter.py \
  "/경로/플레이리스트.mp4" \
  --output-dir "/경로/기록" --audio-output-dir "/경로/MP3" \
  --silence-db -35 --silence-duration 0.25
```

- `--min-minutes`: 한 분절의 최소 길이. 기본 3분.
- `--ideal-minutes`: 3~4분 사이에 무음이 여러 개일 때 우선할 길이. 기본 3.5분.
- `--preferred-max-minutes`: 우선 탐색 창의 끝. 기본 4분. 이 안에 무음이 없으면 최대 6분 창으로 탐색을 넓힌다.
- `--hard-max-minutes`: 무음이 없어도 강제로 분절하는 최대 길이. 기본 6분.
- `--silence-db`: 무음으로 볼 음량. 기본 -38dB.
- `--silence-duration`: 무음이 유지되어야 하는 최소 시간. 기본 0.35초.

### 동작 순서

1. `ffprobe`로 실제 오디오 길이를 확인한다. 영상 뒤에 무음 화면만 길게 붙은 경우 영상 길이가 아니라 오디오 스트림 길이를 사용한다.
2. 무음을 확실(-38dB/0.35초), 보통(-34dB/0.22초), 미세(-30dB/0.12초) 세 단계로 찾는다.
3. 이전 경계에서 3~4분 사이의 후보를 확실한 무음부터 확인하고 3분 30초에 가까운 지점을 고른다.
4. 4분 안에 없으면 최대 6분까지 후보를 찾고, 그래도 없으면 정확히 6분에서 강제로 분절한다.
5. 경계가 정해진 순서대로 MP3를 생성하며 조각 하나마다 기록 파일을 갱신한다. 강제 분절 지점은 로그와 JSON에 `6분-강제`로 표시한다.

### 중단·재실행 기록

- `.silence_split_state.json`: 원본 크기·수정 시각, 무음 탐지 설정, 발견한 무음 지점, 분절 경계와 완성 MP3 파일명을 저장한다.
- 같은 경계의 완성 MP3가 존재하고 실제 재생 길이도 정상이면 인코딩을 생략한다.
- 전체 완료 기록과 모든 MP3가 정상이면 재실행 작업을 즉시 생략한다.
- 원본 파일 내용이나 무음 설정이 바뀌면 기존 기록을 자동으로 무효화한다.

### 한계와 검수 규칙

- 곡 사이에 실제 무음이 전혀 없는 DJ 크로스페이드 영상은 정확한 곡 경계를 알 수 없어 6분 지점에서 강제로 잘릴 수 있다.
- 곡 내부에 긴 무음이 있어도 이전 경계에서 3분이 지나기 전이면 분절하지 않는다.
- 마지막 조각이 최소 설정 시간(기본 3분)보다 짧으면 앞 분절에 합친다.
- 6분 강제 경계 때문에 마지막이 3분 미만이 되는 경우에는 남은 부분을 균등하게 나눠 두 조각 모두 3~6분으로 맞춘다.
- 완성 MP3의 처음·끝 몇 초는 한 번 확인하는 것이 좋다.
- 사용자가 타임스탬프를 제공하면 자동 인식보다 그 타임스탬프를 우선한다.

---

## Codex 세션 실행 문구

```text
일본어자막추출/bgm/README.md를 읽고
<MP4 경로>를 3~4분 사이의 무음 경계 기준으로 MP3 분절해줘.
일본어자막추출/bgm_silence_splitter.py 기록을 재사용해.
```

## Shift Alarm 메뉴바에서 폴더 전체 처리

`shift_alarm` 메뉴의 `🎵 플레이리스트 MP4 → 곡별 MP3 (폴더 선택)`을 누르고 MP4들이 있는 폴더를 선택한다.

- 선택 폴더 바로 아래의 모든 `.mp4`를 순차 처리한다.
- MP3는 같은 폴더에 `<원본명> 분절1.mp3` 형식으로 저장한다.
- 무음 분절 기록은 `.bgm_split_reports/<고유ID>/.silence_split_state.json`에 보관하고, `source_map.json`에 고유 ID와 원본 영상명의 대응 관계를 기록한다.
- 한 영상의 MP3가 전부 생성된 경우에만 원본 MP4를 휴지통으로 옮긴다.
- 실패한 MP4는 원본을 유지하고 다음 영상으로 넘어간다.
- 작업은 일반 Terminal.app에서 실행된다. 창을 닫거나 `Ctrl+C`를 누르면 현재 인식기와 하위 ffmpeg까지 함께 종료한다.
- Shazam과 네트워크 요청은 전혀 사용하지 않는다.

## 분절 MP3의 Shazam 제목 변경

무음 분절이 끝난 MP3의 실제 곡명을 붙이고 싶을 때는 `rename_mp3_with_shazam.py`를 사용한다. 플레이리스트 경계 탐색에는 Shazam을 쓰지 않고, **파일명에 `분절`이 들어간 MP3만** 15초 표본을 한 번 인식한다. 이미 제목이 있는 일반 MP3는 건드리지 않는다.

```bash
일본어자막추출/.venv-shazam/bin/python \
  일본어자막추출/rename_mp3_with_shazam.py \
  "/MP3 폴더"
```

- 성공 즉시 `<아티스트> - <노래제목>.mp3`로 변경한다.
- 이름 충돌 시 `(2)`, `(3)`을 붙이며 기존 파일을 덮어쓰지 않는다.
- 실패한 파일은 원래 이름으로 유지한다.
- `.mp3_shazam_rename_state.json`에 처리 기록을 저장해 재실행 시 완료 파일을 건너뛴다.
- Shift Alarm 메뉴의 `🏷️ MP3 Shazam 제목 변경 (폴더 선택)`에서도 실행할 수 있다.
