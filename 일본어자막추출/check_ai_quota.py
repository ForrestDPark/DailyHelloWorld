#!/usr/bin/env python3
"""파이프라인 시작 전 Codex/Claude 사용량을 확인해, 둘 다 거의 소진된 상태면
경고한다. ★ 2026-09-07: "코덱스랑 클로드 사용량 계산해서 현재 사용량에서 일본어
추출이 가능하지 않으면 추출시작전에 사용량이 부족할거같다고 경고하는 메시지를
띄워주면 좋겠어" 요청 — 오늘 AKDL-370/EBOD-952/MIDV-199 세 편의 학습카드 생성이
"codex/claude 실행 파일을 찾을 수 없음"으로 조용히 실패했던 사고 이후 추가.

shift_alarm/ai_usage.py의 조회 로직을 그대로 재사용한다(중복 방지) — 새 API
호출 방식을 따로 만들지 않는다. generate_summary.py는 codex를 1순위, 실패하면
claude로 자동 전환하므로(ai_exec.py), 둘 다 높은 사용량일 때만 경고한다 — 하나만
높으면 폴백이 여전히 동작하므로 조용히 넘어간다.

경고만 하고 실행을 막지는 않는다(사용자 요청이 "경고 메시지"였지, 중단이 아님) —
값을 못 가져와도(토큰 없음 등) "확인 불가"로 보수적으로 취급해 경고 쪽에 둔다."""
import os
import subprocess
import sys

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "shift_alarm")
)
import ai_usage  # noqa: E402

CODEX_WARN_PERCENT = 85
CLAUDE_WARN_PERCENT = 85


def _codex_status():
    """(사용률 또는 None, 표시용 문자열) — ai_usage.codex_primary_percent 재사용."""
    pct = ai_usage.codex_primary_percent(ai_usage.get_codex_quota())
    if pct is None:
        return None, "확인 불가"
    return pct, f"{pct:.0f}%"


def _claude_status():
    """(사용률 또는 None, 표시용 문자열) — ai_usage.claude_shortest_window_percent
    재사용(ai_exec.py의 엔진 선택과 같은 기준을 쓴다)."""
    pct = ai_usage.claude_shortest_window_percent(ai_usage.get_claude_live_quota())
    if pct is None:
        return None, "확인 불가"
    return pct, f"{pct:.0f}%"


def warn_if_low(file_count):
    """codex_low and claude_low(사용량 임계치 이상 또는 확인 불가)일 때만
    경고를 출력하고 True를 반환한다. 실행을 막지는 않는다."""
    codex_pct, codex_label = _codex_status()
    claude_pct, claude_label = _claude_status()

    codex_low = codex_pct is None or codex_pct >= CODEX_WARN_PERCENT
    claude_low = claude_pct is None or claude_pct >= CLAUDE_WARN_PERCENT

    if not (codex_low and claude_low):
        print(f"🪙 AI 사용량 확인 — Codex {codex_label} · Claude {claude_label} (요약 진행 가능)")
        return False

    message = (
        f"⚠️  Codex({codex_label})·Claude({claude_label}) 사용량이 모두 높아 "
        f"이번에 처리할 {file_count}개 작품의 AI 요약(줄거리·학습카드)이 "
        f"중간에 실패할 수 있습니다. 실패해도 낭독판 EPUB 자체는 whisper "
        f"대사만으로 계속 만들어지지만(★★★★★ 절대 규칙), 학습카드는 나중에 "
        f"쿼터가 회복된 뒤 재실행해야 채워집니다."
    )
    print(message)
    try:
        subprocess.run(
            [
                "osascript", "-e",
                f'display notification "Codex {codex_label} · Claude {claude_label} — '
                f'AI 요약 실패 가능성" with title "⚠️ AI 사용량 부족 경고" sound name "Basso"',
            ],
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass
    return True


if __name__ == "__main__":
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    warn_if_low(count)
