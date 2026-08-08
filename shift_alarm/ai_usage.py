"""Codex/Claude Code 사용량(quota) 조회 — shift_alarm 메뉴바 드롭다운용.

값을 가져올 수 없으면(로그 없음, API 실패, 키체인 없음 등) 추측하지 않고
None을 반환한다. 호출부에서 None이면 "확인 불가"로 표시할 것.

Claude 라이브 quota(get_claude_live_quota)는 macOS 키체인에 Claude Code
자신이 이미 저장해둔 OAuth 토큰으로 비공개 사용량 엔드포인트를 조회한다.
토큰 값은 절대 print/log/알림 문자열에 넣지 말 것 — Authorization 헤더로만 사용.
"""
import glob
import json
import os
import subprocess
import time
import urllib.error
import urllib.request

CODEX_SESSIONS_GLOB = os.path.expanduser("~/.codex/sessions/**/*.jsonl")
CLAUDE_PROJECTS_GLOB = os.path.expanduser("~/.claude/projects/**/*.jsonl")
CLAUDE_STATS_LOOKBACK_SECONDS = 24 * 60 * 60
CLAUDE_USAGE_URL = "https://api.anthropic.com/api/oauth/usage"


def get_codex_quota():
    """최근 Codex 세션에서 가장 최신의 rate_limits를 찾아 반환한다.

    앱과 Codex가 비슷한 시각에 시작되면 가장 최근 세션 파일은 만들어졌지만 첫
    token_count 이벤트는 아직 기록되지 않았을 수 있다. 이때 최신 파일 하나만
    읽으면 이전 세션에 정상 quota가 있어도 ``None``이 되어 다음 12분 갱신까지
    메뉴바에서 Codex가 사라진다. 따라서 세션을 수정 시각 역순으로 확인하고,
    rate_limits가 실제로 들어 있는 첫 파일을 사용한다.
    """
    files = glob.glob(CODEX_SESSIONS_GLOB, recursive=True)
    if not files:
        return None

    for path in sorted(files, key=os.path.getmtime, reverse=True):
        rate_limits = None
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    if '"rate_limits"' not in line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    payload = obj.get("payload", {})
                    if payload.get("type") != "token_count":
                        continue
                    rl = payload.get("rate_limits")
                    if rl:
                        rate_limits = rl
        except OSError:
            continue

        if rate_limits:
            return {
                "primary": rate_limits.get("primary"),
                "secondary": rate_limits.get("secondary"),
            }
    return None


def get_claude_local_stats():
    """최근 24시간 이내 수정된 Claude Code 프로젝트 로그(jsonl)에서
    모델명 / 유저 턴수 / 모델 요청수 / 프롬프트 캐시 적중률을 집계.
    로그가 없으면 None."""
    files = glob.glob(CLAUDE_PROJECTS_GLOB, recursive=True)
    if not files:
        return None
    cutoff = time.time() - CLAUDE_STATS_LOOKBACK_SECONDS
    recent = [f for f in files if os.path.getmtime(f) >= cutoff]
    if not recent:
        return None

    user_turns = 0
    model_requests = 0
    cache_read_total = 0
    cache_creation_total = 0
    input_total = 0
    last_model = None
    last_mtime = 0.0

    for path in recent:
        try:
            mtime = os.path.getmtime(path)
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    msg_type = obj.get("type")
                    if msg_type == "user":
                        user_turns += 1
                    elif msg_type == "assistant":
                        model_requests += 1
                        message = obj.get("message", {})
                        usage = message.get("usage", {}) or {}
                        cache_read_total += usage.get("cache_read_input_tokens", 0) or 0
                        cache_creation_total += usage.get("cache_creation_input_tokens", 0) or 0
                        input_total += usage.get("input_tokens", 0) or 0
                        model = message.get("model")
                        if model and mtime >= last_mtime:
                            last_model = model
                            last_mtime = mtime
        except OSError:
            continue

    if model_requests == 0:
        return None

    cache_denom = cache_read_total + cache_creation_total + input_total
    cache_hit_percent = (
        round(cache_read_total / cache_denom * 100, 1) if cache_denom else None
    )

    return {
        "model": last_model,
        "user_turns": user_turns,
        "model_requests": model_requests,
        "cache_hit_percent": cache_hit_percent,
    }


def _claude_access_token():
    """macOS 키체인에서 Claude Code 자신이 저장해둔 OAuth 액세스 토큰을 읽는다.
    실패 시 None. 반환값은 곧바로 Authorization 헤더에만 쓰고 절대 노출하지 말 것."""
    user = os.environ.get("USER", "")
    if not user:
        return None
    try:
        result = subprocess.run(
            [
                "security", "find-generic-password",
                "-a", user, "-s", "Claude Code-credentials", "-w",
            ],
            capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    try:
        data = json.loads(result.stdout.strip())
    except json.JSONDecodeError:
        return None
    return data.get("claudeAiOauth", {}).get("accessToken")


def get_claude_live_quota():
    """Claude Code 자신의 OAuth 토큰으로 비공개 사용량 엔드포인트를 조회해
    윈도우별 {"utilization": 0~100, "resets_at": ...} 딕셔너리를 반환.
    토큰이 없거나 요청이 실패하면 None."""
    token = _claude_access_token()
    if not token:
        return None
    request = urllib.request.Request(
        CLAUDE_USAGE_URL,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "anthropic-beta": "oauth-2025-04-20",
            "User-Agent": "claude-code/2.1.0",
        },
    )
    token = None  # 헤더에 실어 보냈으니 변수에서 즉시 제거
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            data = json.loads(response.read())
    except (urllib.error.URLError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    return data
