#!/usr/bin/env python3
"""Codex/Claude 비대화형 실행을 하나로 묶어, 한쪽이 실패하면 다른 쪽으로 자동 전환한다.

★ 2026-09-08: "코덱스랑 클로드 사용량 비교해서 더 가용사용량 많은 AI로 추출하도록
파이프라인 수정해" 요청 — 예전엔 codex를 항상 1순위로 고정했는데(2026-08-04), 오늘
Codex가 완전히 소진된 채로 계속 1순위 시도만 하다 claude 폴백까지 같이 걸려
넘어진 사고가 있었다. 이제 매 호출마다 shift_alarm/ai_usage.py의 실시간 사용량
조회로 "지금 더 여유 있는 쪽"을 1순위로 정한다(둘 다 확인 불가하면 기존 관례인
codex로 안전하게 대체). codex든 claude든 실패하면(종료 코드 비정상, 빈 응답,
시간 초과, 실행 파일 없음) 여전히 나머지 하나로 자동 전환한다 — 실패 사유를
특정 문자열로 구분하지 않고 "어떤 이유로든 실패하면 다른 쪽으로" 방식을 쓴다.

★ 2026-08-22: 이 codex exec 호출마다 `~/.codex/config.toml`의 전역 `notify` 훅
(Codex Computer Use용 turn-ended 알림)이 그대로 발동해서, 이 스크립트가
백그라운드에서 조용히 도는 중에도 "Codex 완료" macOS 알림이 계속 떴다(실사용
중 확인 — 코덱스를 직접 켜놓지 않았는데도 알림이 뜨는 원인이었음). 클릭해도
볼 수 있는 세션이 없다(헤드리스 1회성 호출이라 이미 끝나고 사라짐) — 그냥
매번 안 뜨게 이 호출에서만 `-c notify=[]`로 훅을 끈다. 사용자가 직접 여는
대화형 codex 세션에는 영향 없음(전역 설정 파일은 안 건드림).
"""

import os
import subprocess
import sys

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "shift_alarm")
)
import ai_usage  # noqa: E402

CODEX_BIN = "/opt/homebrew/bin/codex"
CLAUDE_BIN = "/opt/homebrew/bin/claude"


def _run_one(engine, prompt, cwd, timeout):
    if engine == "codex":
        cmd = [
            CODEX_BIN, "exec", "--ephemeral", "--sandbox", "read-only",
            "--skip-git-repo-check", "-c", "notify=[]", "-C", str(cwd), "-",
        ]
    else:
        cmd = [
            CLAUDE_BIN, "-p", "--output-format", "text", "--tools", "",
            "--no-session-persistence",
        ]
    return subprocess.run(
        cmd, input=prompt, capture_output=True, text=True,
        timeout=timeout, cwd=str(cwd),
    )


def run_ai_exec(prompt, cwd, timeout=600, primary=None):
    """primary 엔진으로 먼저 시도하고, 실패하면(종료 코드 비정상 또는 빈 응답)
    나머지 하나로 자동 전환한다. 성공한 stdout 텍스트와 실제 사용된 엔진 이름을
    (stdout, engine) 튜플로 반환한다. 둘 다 실패하면 두 엔진의 에러를 합쳐
    RuntimeError를 낸다.

    primary를 안 주면(기본값) 매 호출마다 ai_usage.pick_less_used_engine()으로
    지금 사용량이 더 낮은 쪽을 1순위로 고른다 — 호출 하나하나가 이전 호출들의
    소진 상태를 반영해 적응적으로 움직인다."""
    if primary is None:
        primary = ai_usage.pick_less_used_engine(default="codex")
    order = ["codex", "claude"] if primary == "codex" else ["claude", "codex"]
    errors = []
    for i, engine in enumerate(order):
        try:
            result = _run_one(engine, prompt, cwd, timeout)
        except subprocess.TimeoutExpired:
            errors.append(f"{engine}: 시간 초과({timeout}초)")
            continue
        except FileNotFoundError:
            errors.append(f"{engine}: 실행 파일을 찾을 수 없음")
            continue
        if result.returncode == 0 and result.stdout.strip():
            if i > 0:
                print(f"   ↪️ {order[0]} 실패로 {engine}(으)로 전환해서 처리함")
            return result.stdout, engine
        errors.append(f"{engine}: {result.stderr.strip() or f'종료 코드 {result.returncode}'}")
    raise RuntimeError(" / ".join(errors))
