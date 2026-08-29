"""사용자 BYOK API 키의 암호화 저장과 공급자 연결 확인.

마스터 키는 저장소나 SQLite에 넣지 않고 사용자 홈의 권한 0600 파일에 둔다.
브라우저 API에는 복호화된 키를 절대 반환하지 않으며, WORKER_TOKEN으로 인증된
로컬 워커만 실제 응답 생성 직전에 가져갈 수 있다.
"""
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

MASTER_KEY_PATH = Path(os.environ.get(
    "CHATAPP_BYOK_MASTER_KEY_FILE", os.path.expanduser("~/.tulpachat/byok_master.key")
))
PROVIDERS = ("openai", "anthropic", "gemini")


def _fernet():
    if not MASTER_KEY_PATH.exists():
        MASTER_KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
        MASTER_KEY_PATH.write_bytes(Fernet.generate_key())
        os.chmod(MASTER_KEY_PATH, 0o600)
    return Fernet(MASTER_KEY_PATH.read_bytes().strip())


def encrypt_key(api_key):
    return _fernet().encrypt(api_key.encode("utf-8")).decode("ascii")


def decrypt_key(ciphertext):
    try:
        return _fernet().decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError) as exc:
        raise ValueError("저장된 API 키를 복호화할 수 없습니다") from exc


def key_hint(api_key):
    return f"••••{api_key[-4:]}" if len(api_key) >= 4 else "••••"


def test_provider(provider, api_key, timeout=12):
    """과금되는 생성 호출 대신 각 공급자의 모델 목록 API로 키만 확인한다."""
    if provider == "openai":
        url = "https://api.openai.com/v1/models"
        headers = {"Authorization": f"Bearer {api_key}"}
    elif provider == "anthropic":
        url = "https://api.anthropic.com/v1/models?limit=1"
        headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01"}
    elif provider == "gemini":
        url = "https://generativelanguage.googleapis.com/v1beta/models?pageSize=1"
        headers = {"x-goog-api-key": api_key}
    else:
        raise ValueError("지원하지 않는 AI 공급자입니다")
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise ValueError("API 키가 올바르지 않거나 사용할 권한이 없습니다") from exc
        raise ValueError(f"공급자 연결 확인 실패(HTTP {exc.code})") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise ValueError("AI 공급자에 연결하지 못했습니다. 잠시 후 다시 시도하세요") from exc
    return True
