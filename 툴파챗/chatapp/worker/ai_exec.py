#!/usr/bin/env python3
"""Codex/Claude 비대화형 실행을 하나로 묶어, 한쪽이 실패하면 다른 쪽으로 자동 전환한다.

이직시스템/일본어자막추출과 거의 동일한 파일이다 — 이 저장소 원칙상 프로젝트 간
import를 하지 않고 파일을 복사해서 각자 둔다. codex/claude 폴백·notify 훅 부분을
고치면 다른 두 곳도 같은 버그가 있는지 확인하고 필요하면 동일하게 고친다.
★ 2026-08-25: image_paths 지원(아래)은 이 챗앱 전용 기능이라 의도적으로 다른
두 복사본에는 반영하지 않았다 — 버그 수정이 아니라 이 소비자만 필요한 확장.

기본 우선순위는 claude 1순위, codex 2순위(2026-08-28 변경). claude가
토큰/쿼터 소진 등으로 실패해도 파이프라인이 멈추지 않도록 같은 프롬프트를
codex로 재시도한다. 담당자 분류처럼 지연에 민감한 호출은 fallback=False로
한 엔진만 짧게 호출할 수도 있다.

codex exec 호출마다 `~/.codex/config.toml`의 전역 `notify` 훅(Codex Computer
Use용 turn-ended 알림)이 그대로 발동해 헤드리스 호출에서도 "Codex 완료" macOS
알림이 뜨는 문제가 있어(이미 겪음, 2026-08-22), `-c notify=[]`로 이 호출에서만
훅을 끈다."""

import base64
import json
import mimetypes
import os
import subprocess
import urllib.error
import urllib.request

CODEX_BIN = "/opt/homebrew/bin/codex"
CLAUDE_BIN = "/opt/homebrew/bin/claude"


def _data_url(path):
    mime = mimetypes.guess_type(str(path))[0] or "image/jpeg"
    with open(path, "rb") as image_file:
        encoded = base64.b64encode(image_file.read()).decode("ascii")
    return mime, f"data:{mime};base64,{encoded}", encoded


def _post_json(url, headers, payload, timeout):
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"), method="POST",
        headers={"Content-Type": "application/json", **headers},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode("utf-8"))
            message = detail.get("error", {}).get("message") or str(detail)
        except Exception:  # noqa: BLE001
            message = f"HTTP {exc.code}"
        raise RuntimeError(message) from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"AI API 연결 실패: {exc}") from exc


def run_provider_api(provider, api_key, prompt, timeout=120, image_paths=None):
    """사용자 자신의 API 키로 텍스트·이미지 대화를 생성한다.

    CLI와 달리 Bash·파일 도구는 전혀 제공하지 않는다. 이미지가 있을 때만
    워커가 이미 허용한 업로드 파일을 base64 입력으로 첨부한다.
    """
    image_paths = image_paths or []
    if provider == "openai":
        content = [{"type": "input_text", "text": prompt}]
        for path in image_paths:
            _mime, data_url, _encoded = _data_url(path)
            content.append({"type": "input_image", "image_url": data_url})
        data = _post_json(
            "https://api.openai.com/v1/responses",
            {"Authorization": f"Bearer {api_key}"},
            {"model": os.environ.get("CHATAPP_OPENAI_MODEL", "gpt-5-mini"),
             "input": [{"role": "user", "content": content}]}, timeout,
        )
        texts = [part.get("text", "") for item in data.get("output", [])
                 for part in item.get("content", []) if part.get("type") == "output_text"]
    elif provider == "anthropic":
        content = []
        for path in image_paths:
            mime, _data_url_value, encoded = _data_url(path)
            content.append({"type": "image", "source": {"type": "base64", "media_type": mime, "data": encoded}})
        content.append({"type": "text", "text": prompt})
        data = _post_json(
            "https://api.anthropic.com/v1/messages",
            {"x-api-key": api_key, "anthropic-version": "2023-06-01"},
            {"model": os.environ.get("CHATAPP_ANTHROPIC_MODEL", "claude-haiku-4-5-20251001"),
             "max_tokens": 1600, "messages": [{"role": "user", "content": content}]}, timeout,
        )
        texts = [part.get("text", "") for part in data.get("content", []) if part.get("type") == "text"]
    elif provider == "gemini":
        parts = [{"text": prompt}]
        for path in image_paths:
            mime, _data_url_value, encoded = _data_url(path)
            parts.append({"inline_data": {"mime_type": mime, "data": encoded}})
        model = os.environ.get("CHATAPP_GEMINI_MODEL", "gemini-2.5-flash")
        data = _post_json(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            {"x-goog-api-key": api_key}, {"contents": [{"role": "user", "parts": parts}]}, timeout,
        )
        texts = [part.get("text", "") for candidate in data.get("candidates", [])
                 for part in candidate.get("content", {}).get("parts", []) if part.get("text")]
    else:
        raise RuntimeError("지원하지 않는 AI 공급자입니다")
    output = "\n".join(texts).strip()
    if not output:
        raise RuntimeError("AI 공급자가 빈 응답을 반환했습니다")
    return output, provider


def _run_one(engine, prompt, cwd, timeout, image_paths=None, allow_tools=None, add_dirs=None):
    image_paths = image_paths or []
    # ★ 2026-08-25: 손동주(맥북 파일 정리 담당 페르소나) 지원을 위해 이미지
    # 첨부와 별개로 도구/디렉터리를 명시적으로 지정할 수 있게 일반화했다.
    # 실제 파일 이동·삭제는 이 함수가 직접 하지 않는다 — AI에게는 Read/Glob
    # 같은 "읽기" 도구만 준다. 실제 파일 시스템 변경은 persona_worker.py가
    # AI 응답에서 계획(JSON)만 뽑아내 사용자 승인 후 결정론적 코드로
    # 수행한다(AI에게 Bash/mv/rm 권한을 직접 주지 않음 — 프롬프트 인젝션이나
    # 모델 실수로 홈 폴더가 훼손되는 걸 막기 위한 설계).
    allow_tools = set(allow_tools or [])
    add_dirs = {str(d) for d in (add_dirs or [])}
    if image_paths:
        allow_tools.add("Read")
        add_dirs |= {os.path.dirname(str(p)) for p in image_paths}
    if engine == "codex":
        # ★ codex exec는 -i/--image로 이미지를 직접 첨부할 수 있다(codex exec
        # --help로 확인). -C(작업 디렉터리) 앞에 둬서 가변 인자가 뒤따르는
        # 옵션을 삼키지 않게 한다(--add-dir이 프롬프트를 삼켰던 사례 참고).
        cmd = [CODEX_BIN, "exec", "--ephemeral", "--sandbox", "read-only", "--skip-git-repo-check"]
        for path in image_paths:
            cmd += ["-i", str(path)]
        cmd += ["-c", "notify=[]", "-C", str(cwd), "-"]
    else:
        # ★ claude CLI엔 이미지 첨부 플래그가 없다 — Read 도구로 직접 읽게
        # 한다(이직시스템 fetch_job_detail_via_screenshot()과 같은 패턴).
        # 이미지/특수 도구가 없으면 기존처럼 도구를 전부 끈 순수 텍스트 모드.
        cmd = [CLAUDE_BIN, "-p", "--output-format", "text", "--no-session-persistence"]
        if allow_tools:
            cmd += ["--allowedTools", ",".join(sorted(allow_tools))]
            for directory in sorted(add_dirs):
                cmd += ["--add-dir", directory]
        else:
            cmd += ["--tools", ""]
        # Claude Code 2.1.x는 가변 인자 옵션(--tools/--add-dir) 뒤의 stdin을
        # 프롬프트로 인식하지 못할 수 있다. 옵션 종료 구분자를 명시해 대화
        # 내용은 argv가 아니라 기존처럼 stdin으로 안전하게 전달한다.
        cmd += ["--"]
    return subprocess.run(
        cmd, input=prompt, capture_output=True, text=True,
        timeout=timeout, cwd=str(cwd),
    )


def run_ai_exec(
    prompt, cwd, timeout=600, primary="claude", validator=None,
    image_paths=None, allow_tools=None, add_dirs=None, fallback=True,
):
    """primary 엔진으로 먼저 시도하고, 실패하면(종료 코드 비정상 또는 빈 응답)
    나머지 하나로 자동 전환한다. 성공한 stdout 텍스트와 실제 사용된 엔진 이름을
    (stdout, engine) 튜플로 반환한다. 둘 다 실패하면 두 엔진의 에러를 합쳐
    RuntimeError를 낸다.

    image_paths: 로컬 이미지 파일 경로 목록(선택). 지정하면 두 엔진 모두
    프롬프트와 함께 이미지를 실제로 "보고" 응답한다.
    allow_tools/add_dirs: claude 엔진 전용 — 이미지 외에 추가로 열어줄 도구
    이름 목록과 그 도구가 접근할 디렉터리 목록(예: 손동주의 Read/Glob 홈
    폴더 접근)."""
    order = ["codex", "claude"] if primary == "codex" else ["claude", "codex"]
    if not fallback:
        order = order[:1]
    errors = []
    for i, engine in enumerate(order):
        try:
            result = _run_one(
                engine, prompt, cwd, timeout,
                image_paths=image_paths, allow_tools=allow_tools, add_dirs=add_dirs,
            )
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
