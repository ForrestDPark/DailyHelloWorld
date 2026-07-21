# 손자병법 구절 해석 — 전략지형도 코드

## 구성
- `strategy_map_lib.py` — 공통 라이브러리 (지형 렌더링, 병력 scatter, 화살표, 하단 3박스, 범례, 텍스트 폭 실측 기반 자동 줄바꿈/폰트 축소)
- `map_jingxing.py` — 정형 전투(BCE 204) 전략지형도
- `map_agincourt.py` — 아쟁쿠르 전투(1415) 전략지형도
- 각 구절마다 `map_<전투명>.py` 파일을 새로 추가하는 방식으로 확장

## 실행
```
cd 손자병법
python3 map_<전투명>.py
```
같은 폴더에 `<전투명>_map.png`가 생성된다. 폴더 내에서 바로 실행 가능(상대경로 기반).

## 규칙 (전략지형도 프롬프트 기준)
- 캔버스 24x20, dpi 155, 상단 지도(8.2~19.2) + 하단 정보 3박스(0.3~7.9)
- 하단 3박스는 캔버스 정중앙 정렬 (`LX = (24 - (3*BW + 2*GAP)) / 2`)
- 박스 안 텍스트는 실제 렌더 폭을 측정해 줄바꿈(`wrap_by_width`)하고,
  내용이 많으면 폰트 크기를 자동으로 줄여 박스 밖으로 넘치지 않게 한다
  (`draw_analysis_box`/`draw_legend_box` 내부 auto-fit 루프).
- 한자는 되도록 줄이고, 꼭 써야 할 때는 `hj('한자','독음')` 헬퍼로 옆에 독음을 병기.
- 병력은 직사각형 배열 금지, scatter로 자연스러운 포진.
- 기병은 🐎 이모지(Apple Color Emoji, PIL로 래스터화 후 OffsetImage).
- 별 마커 금지, 요충지는 원형 점선(`marker_point`).

## 폰트
- 본문: `/System/Library/Fonts/AppleSDGothicNeo.ttc` (한글+대부분 한자)
- 폴백(누락 한자용): `/System/Library/Fonts/STHeiti Medium.ttc`
- 이모지: `/System/Library/Fonts/Apple Color Emoji.ttc`

## GitHub 배포
저장소 자체가 이미 git 연결되어 있으므로 GitHub API 없이 `git add/commit/push`로 진행.
raw URL 형식:
```
https://raw.githubusercontent.com/ForrestDPark/DailyHelloWorld/main/손자병법/<파일명>
```
(한글 폴더명은 URL에서 percent-encoding 필요: `손자병법` → `%EC%86%90%EC%9E%90%EB%B3%91%EB%B2%95`)
