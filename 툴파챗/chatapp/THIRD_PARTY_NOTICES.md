# Third-party notices

## 중화민국 교육부 표준 해서체

채팅 메시지 본문의 한자에는 중화민국 교육부가 제공하는 `교육부標準楷書字型檔
(Version 5.1)` 원본을 변형 없이 사용합니다(`손자병법/site`가 쓰는 것과 동일한
파일).

- 저작자·출처: 중화민국 교육부
- 라이선스: Creative Commons 저작자표시-변경금지 3.0 대만
- 공식 배포: https://language.moe.gov.tw/material/info?m=9fe3fe82-8bbf-44c0-961d-873ea079e284
- 포함 파일: `static/fonts/TW-MOE-Kai-v5.1.ttf`

## Noto Sans JP

일본어 선생님 메시지와 가나가 포함된 채팅 메시지에는 일본어 CJK 자형이
수록된 `Noto Sans JP`를 사용합니다.

- 저작권: Copyright 2014-2021 Adobe, Reserved Font Name `Source`
- 라이선스: SIL Open Font License 1.1
- 공식 소스: https://github.com/google/fonts/tree/main/ofl/notosansjp
- 라이선스 원문: https://github.com/google/fonts/blob/main/ofl/notosansjp/OFL.txt
- 포함 파일: `static/fonts/NotoSansJP-wght.woff2`

## KANJIDIC2

일본어 메시지의 한자를 눌렀을 때 표시하는 음독·훈독 데이터는 Electronic
Dictionary Research and Development Group(EDRDG)의 KANJIDIC2를 가공해
사용합니다.

- 저작자·출처: Electronic Dictionary Research and Development Group
- 라이선스: Creative Commons Attribution-ShareAlike 4.0 International
- 공식 프로젝트: https://www.edrdg.org/wiki/KANJIDIC_Project.html
- 라이선스: https://creativecommons.org/licenses/by-sa/4.0/
- 가공 파일: `static/data/kanjidic-readings.json`

## libhangul Hanja dictionary

채팅 한자 팝업과 단어장에 표시하는 한국 한자음·뜻은 libhangul의
`data/hanja/hanja.txt`를 가공해 사용합니다.

- 저작권: Copyright © 2005–2006 Choe Hwanjin
- 라이선스: BSD 3-Clause
- 공식 소스: https://github.com/libhangul/libhangul/blob/main/data/hanja/hanja.txt
- 가공 파일: `static/data/kanjidic-readings.json`

## OpenCC Japanese Shinjitai mapping

libhangul에서 뜻이 정자체에만 등록된 일본 신자체는 OpenCC의
`JPShinjitaiCharacters.txt`로 정자체와 연결해 한국어 뜻을 표시합니다.

- 저작자·출처: Open Chinese Convert(OpenCC) contributors
- 라이선스: Apache License 2.0
- 공식 소스: https://github.com/BYVoid/OpenCC/blob/master/data/dictionary/JPShinjitaiCharacters.txt
- 가공 파일: `static/data/kanjidic-readings.json`
