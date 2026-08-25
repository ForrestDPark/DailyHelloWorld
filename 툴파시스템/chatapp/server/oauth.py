"""Google/카카오 소셜 로그인 — 표준 OAuth 2.0 authorization code flow.

★ 2026-08-26: "구글이랑 카카오 로그인 가능하게 해달라" 요청. requests/authlib
같은 외부 라이브러리 없이 표준 라이브러리(urllib)만 쓴다 — server/db.py·
auth.py와 같은 "의존성 최소화" 원칙.

두 프로바이더 모두 리다이렉트 URI를 미리 콘솔에 고정 등록해야 해서, Cloudflare
Quick Tunnel(재시작마다 URL이 바뀜)로는 애초에 못 쓴다 — PUBLIC_BASE_URL이
고정 도메인(예: https://chat.tulpa-chat.site)을 가리켜야 동작한다. 이 값이나
각 프로바이더의 CLIENT_ID/SECRET이 비어 있으면 해당 로그인은 그냥 비활성
상태로 남는다(*_enabled() 참고) — 프론트가 그 값을 보고 버튼을 숨긴다."""
import json
import os
import urllib.error
import urllib.parse
import urllib.request

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
# ★ 카카오는 REST API 키가 client_id 역할을 한다. Client Secret은 "카카오
# 로그인 > 보안" 설정에서 켰을 때만 필요(기본은 꺼져 있음) — 켜지 않았다면
# KAKAO_CLIENT_SECRET을 비워둬도 된다.
KAKAO_CLIENT_ID = os.environ.get("KAKAO_CLIENT_ID", "")
KAKAO_CLIENT_SECRET = os.environ.get("KAKAO_CLIENT_SECRET", "")
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

KAKAO_AUTH_URL = "https://kauth.kakao.com/oauth/authorize"
KAKAO_TOKEN_URL = "https://kauth.kakao.com/oauth/token"
KAKAO_USERINFO_URL = "https://kapi.kakao.com/v2/user/me"


def google_enabled():
    return bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET and PUBLIC_BASE_URL)


def kakao_enabled():
    return bool(KAKAO_CLIENT_ID and PUBLIC_BASE_URL)


def google_redirect_uri():
    return f"{PUBLIC_BASE_URL}/api/auth/google/callback"


def kakao_redirect_uri():
    return f"{PUBLIC_BASE_URL}/api/auth/kakao/callback"


def _post_form(url, data):
    body = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def _get_json(url, access_token):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {access_token}"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def google_auth_url(state):
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": google_redirect_uri(),
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "prompt": "select_account",
    }
    return f"{GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}"


class OAuthError(Exception):
    pass


def google_exchange(code):
    """인가 코드를 액세스 토큰으로 교환하고 프로필을 가져온다.
    반환: {"external_id": 구글 sub, "name": 표시 이름}"""
    try:
        token = _post_form(GOOGLE_TOKEN_URL, {
            "code": code,
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "redirect_uri": google_redirect_uri(),
            "grant_type": "authorization_code",
        })
        profile = _get_json(GOOGLE_USERINFO_URL, token["access_token"])
    except (urllib.error.URLError, urllib.error.HTTPError, KeyError, json.JSONDecodeError) as exc:
        raise OAuthError(str(exc)) from exc
    return {"external_id": profile["sub"], "name": profile.get("name") or profile.get("email") or "google_user"}


def kakao_auth_url(state):
    params = {
        "client_id": KAKAO_CLIENT_ID,
        "redirect_uri": kakao_redirect_uri(),
        "response_type": "code",
        "state": state,
    }
    return f"{KAKAO_AUTH_URL}?{urllib.parse.urlencode(params)}"


def kakao_exchange(code):
    """반환: {"external_id": 카카오 회원번호, "name": 표시 이름(닉네임)}"""
    data = {
        "grant_type": "authorization_code",
        "client_id": KAKAO_CLIENT_ID,
        "redirect_uri": kakao_redirect_uri(),
        "code": code,
    }
    if KAKAO_CLIENT_SECRET:
        data["client_secret"] = KAKAO_CLIENT_SECRET
    try:
        token = _post_form(KAKAO_TOKEN_URL, data)
        profile = _get_json(KAKAO_USERINFO_URL, token["access_token"])
    except (urllib.error.URLError, urllib.error.HTTPError, KeyError, json.JSONDecodeError) as exc:
        raise OAuthError(str(exc)) from exc
    kakao_account = profile.get("kakao_account") or {}
    nickname = (kakao_account.get("profile") or {}).get("nickname")
    return {"external_id": str(profile["id"]), "name": nickname or f"kakao_{profile['id']}"}
