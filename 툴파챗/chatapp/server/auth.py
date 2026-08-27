"""회원가입/로그인용 비밀번호 해시·세션 헬퍼.

★ 2026-08-26: "다른 사용자들도 메시지를 남길 수 있으면 좋겠다"는 요청으로
단일 소유자 Basic Auth(APP_USERNAME/APP_PASSWORD)를 다중 계정 로그인으로
확장하면서 분리했다. 표준 라이브러리(hashlib/secrets)만 쓴다 — 이 저장소
전반의 "클라우드에 배포되는 부분은 의존성 최소화" 원칙(server/db.py와 동일).

비밀번호는 PBKDF2-HMAC-SHA256(계정마다 랜덤 salt, 200,000회 반복)으로
저장한다 — bcrypt/argon2 같은 전용 라이브러리를 새로 추가하지 않고도
평문 저장보다 충분히 안전한 선에서 표준 라이브러리로 해결."""
import datetime
import hashlib
import secrets

PBKDF2_ITERATIONS = 200_000
SESSION_MAX_AGE_SECONDS = 60 * 60 * 24 * 180  # 180일 — READ_SHARE_TOKEN 쿠키와 동일 정책


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def hash_password(password):
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), PBKDF2_ITERATIONS).hex()
    return salt, digest


def verify_password(password, salt, expected_digest):
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), PBKDF2_ITERATIONS).hex()
    return secrets.compare_digest(digest, expected_digest)


def create_session(conn, user_id):
    token = secrets.token_hex(32)
    now = _now()
    expires_at = now + datetime.timedelta(seconds=SESSION_MAX_AGE_SECONDS)
    conn.execute(
        "INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
        (token, user_id, now.isoformat(timespec="seconds"), expires_at.isoformat(timespec="seconds")),
    )
    conn.commit()
    return token


def get_session_user(conn, token):
    """세션 토큰으로 사용자 row를 찾는다. 만료됐으면 세션을 지우고 None."""
    if not token:
        return None
    row = conn.execute(
        """
        SELECT sessions.expires_at AS expires_at, users.id AS id, users.username AS username,
               users.is_owner AS is_owner
        FROM sessions JOIN users ON users.id = sessions.user_id
        WHERE sessions.token = ?
        """,
        (token,),
    ).fetchone()
    if not row:
        return None
    expires_at = datetime.datetime.fromisoformat(row["expires_at"])
    if expires_at < _now():
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
        conn.commit()
        return None
    return {"id": row["id"], "username": row["username"], "is_owner": bool(row["is_owner"])}


def delete_session(conn, token):
    conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
    conn.commit()
