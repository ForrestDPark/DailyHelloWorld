#!/usr/bin/env python3
"""Codex/Claude 비대화형 실행을 하나로 묶어, 한쪽이 실패하면 다른 쪽으로 자동 전환한다.

기본 우선순위는 codex 1순위, claude 2순위 (2026-08-04 확정). codex가 토큰/쿼터
소진(usage limit) 등으로 실패해도 요약·번역 보정 파이프라인이 멈추지 않도록,
같은 프롬프트를 claude로 그대로 재시도한다. 실패 사유를 특정 문자열로 구분하지
않고 "codex가 어떤 이유로든 실패하면 claude로" 방식을 쓴다 — usage limit 에러
메시지가 버전에 따라 바뀔 수 있어서 문자열 매칭보다 안전하다.

★ 2026-08-22: 이 codex exec 호출마다 `~/.codex/config.toml`의 전역 `notify` 훅
(Codex Computer Use용 turn-ended 알림)이 그대로 발동해서, 이 스크립트가
백그라운드에서 조용히 도는 중에도 "Codex 완료" macOS 알림이 계속 떴다(실사용
중 확인 — 코덱스를 직접 켜놓지 않았는데도 알림이 뜨는 원인이었음). 클릭해도
볼 수 있는 세션이 없다(헤드리스 1회성 호출이라 이미 끝나고 사라짐) — 그냥
매번 안 뜨게 이 호출에서만 `-c notify=[]`로 훅을 끈다. 사용자가 직접 여는
대화형 codex 세션에는 영향 없음(전역 설정 파일은 안 건드림).
"""

import subprocess

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


def run_ai_exec(prompt, cwd, timeout=600, primary="codex", validator=None):
    """primary 엔진으로 먼저 시도하고, 실패하면(종료 코드 비정상 또는 빈 응답)
    나머지 하나로 자동 전환한다. 성공한 stdout 텍스트와 실제 사용된 엔진 이름을
    (stdout, engine) 튜플로 반환한다. 둘 다 실패하면 두 엔진의 에러를 합쳐
    RuntimeError를 낸다."""
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
        output = result.stdout.strip()
        if result.returncode == 0 and output and (validator is None or validator(output)):
            if i > 0:
                print(f"   ↪️ {order[0]} 실패로 {engine}(으)로 전환해서 처리함")
            return result.stdout, engine
        if result.returncode == 0 and output and validator is not None:
            errors.append(f"{engine}: 응답 형식 검증 실패(도구 로그 또는 필수 섹션 누락)")
            continue
        errors.append(f"{engine}: {result.stderr.strip() or f'종료 코드 {result.returncode}'}")
    raise RuntimeError(" / ".join(errors))
