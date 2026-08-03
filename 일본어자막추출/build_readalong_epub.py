#!/usr/bin/env python3
"""이전 Claude 프로토타입 명령을 위한 호환 진입점.

실제 구현은 Apple Books의 고정 레이아웃 Read Aloud 제약을 따르는
build_readaloud_epub.py 하나로 통합했다.
"""

from build_readaloud_epub import main


if __name__ == "__main__":
    print("ℹ️ build_readalong_epub.py는 호환용 이름입니다. build_readaloud_epub.py를 실행합니다.")
    main()
