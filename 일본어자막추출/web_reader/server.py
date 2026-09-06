#!/usr/bin/env python3
"""비공개 EPUB 웹 서재. 외부 패키지 없이 실행된다."""

from __future__ import annotations

import argparse
import base64
import datetime
import hashlib
import hmac
import json
import mimetypes
import os
import posixpath
import secrets
import sqlite3
import time
import urllib.parse
import zipfile
from dataclasses import dataclass
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"
DEFAULT_FINAL_DIR = Path("/Users/forrestdpark/Desktop/BlogImage/av완성작")
DEFAULT_FALLBACK_DIR = ROOT.parent / "library"
STATE_DIR = Path(os.environ.get("JP_WEB_READER_STATE_DIR", "~/.japanese_epub_web")).expanduser()
SESSION_COOKIE = "jp_reader_session"
CHAT_SESSION_COOKIE = "tulpa_session"
SESSION_TTL = 60 * 60 * 24 * 30
MAX_JSON = 64 * 1024
XML_NS = {"c": "urn:oasis:names:tc:opendocument:xmlns:container", "opf": "http://www.idpf.org/2007/opf", "dc": "http://purl.org/dc/elements/1.1/"}


def _safe_member(name: str) -> str:
    name = urllib.parse.unquote(name).replace("\\", "/").lstrip("/")
    normalized = posixpath.normpath(name)
    if normalized in {"", "."} or normalized == ".." or normalized.startswith("../"):
        raise ValueError("잘못된 EPUB 내부 경로입니다")
    return normalized


def _book_id(path: Path) -> str:
    return hashlib.sha256(str(path.resolve()).encode()).hexdigest()[:20]


def _product_key(path: Path) -> str:
    stem = path.stem.replace("_낭독판", "").replace("_읽어주기", "")
    return stem.split(" — ", 1)[0].strip().casefold()


@dataclass(frozen=True)
class Book:
    id: str
    path: Path
    title: str
    opf_path: str
    spine: tuple[str, ...]
    audio: tuple[tuple[dict, ...], ...]
    cover: str | None
    modified: float
    size: int

    def public(self, progress: dict | None = None, base_path: str = "") -> dict:
        return {
            "id": self.id, "title": self.title, "chapters": len(self.spine),
            "modified": int(self.modified), "size": self.size,
            "cover_url": f"{base_path}/api/books/{self.id}/cover" if self.cover else None,
            "has_audio": any(self.audio),
            "progress": progress or {"spine_index": 0, "percent": 0},
            "read_url": f"{base_path}/?book={self.id}",
        }


def _clock_seconds(value: str | None) -> float:
    """SMIL 시각(00:00:01.250, 1.25s 등)을 초로 바꾼다."""
    if not value:
        return 0.0
    value = value.strip().lower().removeprefix("npt=")
    try:
        if value.endswith("ms"):
            return float(value[:-2]) / 1000
        if value.endswith("s"):
            return float(value[:-1])
        parts = [float(part) for part in value.split(":")]
        return sum(part * (60 ** index) for index, part in enumerate(reversed(parts)))
    except ValueError:
        return 0.0


def _smil_audio(zf: zipfile.ZipFile, smil_member: str) -> tuple[dict, ...]:
    try:
        root = ET.fromstring(zf.read(smil_member))
    except (KeyError, ValueError, ET.ParseError):
        return ()
    result = []
    for par in root.findall(".//{*}par"):
        node = par.find("{*}audio")
        text_node = par.find("{*}text")
        if node is None:
            continue
        src = (node.get("src") or "").split("#", 1)[0]
        if not src:
            continue
        try:
            member = _safe_member(posixpath.join(posixpath.dirname(smil_member), src))
        except ValueError:
            continue
        begin = _clock_seconds(node.get("clipBegin"))
        end = _clock_seconds(node.get("clipEnd"))
        text_src = text_node.get("src") if text_node is not None else ""
        target = urllib.parse.unquote(text_src.split("#", 1)[1]) if "#" in text_src else None
        result.append({"member": member, "begin": begin, "end": end or None, "target": target})
    return tuple(result)


def parse_book(path: Path) -> Book:
    with zipfile.ZipFile(path) as zf:
        container = ET.fromstring(zf.read("META-INF/container.xml"))
        node = container.find(".//c:rootfile", XML_NS)
        if node is None or not node.get("full-path"):
            raise ValueError("OPF 경로가 없습니다")
        opf_path = _safe_member(node.get("full-path", ""))
        package = ET.fromstring(zf.read(opf_path))
        title_node = package.find(".//dc:title", XML_NS)
        title = (title_node.text or "").strip() if title_node is not None else path.stem
        title = title or path.stem
        opf_dir = posixpath.dirname(opf_path)
        items: dict[str, dict] = {}
        for item in package.findall(".//opf:manifest/opf:item", XML_NS):
            item_id, href = item.get("id"), item.get("href")
            if item_id and href:
                member = _safe_member(posixpath.join(opf_dir, urllib.parse.unquote(href)))
                items[item_id] = {"member": member, "media_type": item.get("media-type", ""), "properties": item.get("properties", ""), "overlay": item.get("media-overlay")}
        spine_items = [items[ref.get("idref")] for ref in package.findall(".//opf:spine/opf:itemref", XML_NS) if ref.get("idref") in items]
        spine = tuple(item["member"] for item in spine_items)
        audio = tuple(_smil_audio(zf, items[item["overlay"]]["member"]) if item.get("overlay") in items else () for item in spine_items)
        cover = next((v["member"] for v in items.values() if "cover-image" in v["properties"].split()), None)
        if not cover:
            meta = package.find(".//opf:metadata/opf:meta[@name='cover']", XML_NS)
            if meta is not None and meta.get("content") in items:
                cover = items[meta.get("content")]["member"]
        if not cover:
            cover = next((v["member"] for key, v in items.items() if v["media_type"].startswith("image/") and "cover" in key.casefold()), None)
        stat = path.stat()
        return Book(_book_id(path), path.resolve(), title, opf_path, spine, audio, cover, stat.st_mtime, stat.st_size)


class Library:
    def __init__(self, roots: list[Path]):
        self.roots = roots
        self.books: dict[str, Book] = {}
        self.scan()

    def scan(self) -> None:
        selected: dict[str, Path] = {}
        for root in self.roots:
            if not root.exists():
                continue
            for path in sorted(root.rglob("*.epub")):
                key = _product_key(path)
                current = selected.get(key)
                if current is None or ("낭독판" in path.stem and "낭독판" not in current.stem and "읽어주기" not in current.stem):
                    selected[key] = path
        books = {}
        for path in selected.values():
            try:
                book = parse_book(path)
                books[book.id] = book
            except (OSError, KeyError, ValueError, zipfile.BadZipFile, ET.ParseError):
                continue
        self.books = books


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS progress (book_id TEXT PRIMARY KEY, spine_index INTEGER NOT NULL DEFAULT 0, percent REAL NOT NULL DEFAULT 0, updated_at INTEGER NOT NULL)")

    def connect(self):
        return sqlite3.connect(self.path, timeout=10)

    def get(self, book_id: str) -> dict:
        with self.connect() as db:
            row = db.execute("SELECT spine_index, percent, updated_at FROM progress WHERE book_id=?", (book_id,)).fetchone()
        return {"spine_index": row[0], "percent": row[1], "updated_at": row[2]} if row else {"spine_index": 0, "percent": 0}

    def save(self, book_id: str, index: int, percent: float) -> dict:
        now = int(time.time())
        with self.connect() as db:
            db.execute("INSERT INTO progress(book_id,spine_index,percent,updated_at) VALUES(?,?,?,?) ON CONFLICT(book_id) DO UPDATE SET spine_index=excluded.spine_index,percent=excluded.percent,updated_at=excluded.updated_at", (book_id, index, percent, now))
        return {"spine_index": index, "percent": percent, "updated_at": now}


def load_secret() -> bytes:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    path = STATE_DIR / "session.secret"
    if path.exists():
        return path.read_bytes()
    value = secrets.token_bytes(32)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as fp:
        fp.write(value)
    return value


def sign_session(secret: bytes) -> str:
    payload = str(int(time.time()) + SESSION_TTL)
    sig = hmac.new(secret, payload.encode(), hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(f"{payload}.{sig}".encode()).decode()


def valid_session(secret: bytes, value: str) -> bool:
    try:
        raw = base64.urlsafe_b64decode(value.encode()).decode()
        expires, signature = raw.split(".", 1)
        expected = hmac.new(secret, expires.encode(), hashlib.sha256).hexdigest()
        return int(expires) >= int(time.time()) and hmac.compare_digest(signature, expected)
    except (ValueError, UnicodeError):
        return False


class ReaderHandler(BaseHTTPRequestHandler):
    server_version = "JapaneseEpubReader/1.0"

    @property
    def app(self):
        return self.server.app  # type: ignore[attr-defined]

    def log_message(self, fmt, *args):
        print(f"[{self.log_date_time_string()}] {fmt % args}")

    def _json(self, status: int, data: dict | list, headers: dict | None = None):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for key, value in (headers or {}).items(): self.send_header(key, value)
        self.end_headers(); self.wfile.write(body)

    def _body(self) -> dict:
        length = min(int(self.headers.get("Content-Length", "0")), MAX_JSON)
        return json.loads(self.rfile.read(length) or b"{}")

    def _authenticated(self) -> bool:
        jar = cookies.SimpleCookie(self.headers.get("Cookie", ""))
        morsel = jar.get(SESSION_COOKIE)
        if morsel and valid_session(self.app.secret, morsel.value):
            return True
        chat_session = jar.get(CHAT_SESSION_COOKIE)
        return bool(chat_session and self.app.valid_chat_owner_session(chat_session.value))

    def _path(self) -> str:
        path = urllib.parse.urlsplit(self.path).path
        if self.app.base_path and (path == self.app.base_path or path.startswith(self.app.base_path + "/")):
            return path[len(self.app.base_path):] or "/"
        return path

    def _need_auth(self) -> bool:
        if self._authenticated(): return True
        self._json(401, {"ok": False, "detail": "로그인이 필요합니다"}); return False

    def do_POST(self):
        path = self._path()
        if path == "/api/login":
            try: supplied = str(self._body().get("password", ""))
            except (json.JSONDecodeError, ValueError): return self._json(400, {"ok": False})
            if not hmac.compare_digest(supplied, self.app.password):
                time.sleep(0.15); return self._json(401, {"ok": False, "detail": "비밀번호가 올바르지 않습니다"})
            token = sign_session(self.app.secret)
            secure = "; Secure" if self.headers.get("X-Forwarded-Proto", "").lower() == "https" else ""
            return self._json(200, {"ok": True}, {"Set-Cookie": f"{SESSION_COOKIE}={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={SESSION_TTL}{secure}"})
        if path == "/api/logout":
            return self._json(200, {"ok": True}, {"Set-Cookie": f"{SESSION_COOKIE}=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0"})
        if path == "/api/rescan" and self._need_auth():
            self.app.library.scan(); return self._json(200, {"ok": True, "count": len(self.app.library.books)})
        self._json(404, {"ok": False})

    def do_PUT(self):
        path = self._path()
        parts = path.strip("/").split("/")
        if len(parts) == 4 and parts[:2] == ["api", "books"] and parts[3] == "progress" and self._need_auth():
            book = self.app.library.books.get(parts[2])
            if not book: return self._json(404, {"detail": "책을 찾을 수 없습니다"})
            try:
                data = self._body(); index = int(data.get("spine_index", 0)); percent = float(data.get("percent", 0))
            except (json.JSONDecodeError, TypeError, ValueError): return self._json(400, {"detail": "진행 정보가 올바르지 않습니다"})
            index = max(0, min(index, max(0, len(book.spine) - 1))); percent = max(0, min(percent, 100))
            return self._json(200, {"ok": True, **self.app.store.save(book.id, index, percent)})
        self._json(404, {"ok": False})

    def do_GET(self):
        path = self._path()
        if path == "/api/session": return self._json(200, {"authenticated": self._authenticated()})
        if path == "/api/books" and self._need_auth():
            books = sorted(self.app.library.books.values(), key=lambda b: b.modified, reverse=True)
            return self._json(200, [b.public(self.app.store.get(b.id), self.app.base_path) for b in books])
        if path.startswith("/api/books/") and self._need_auth(): return self._book_route(path)
        return self._static(path)

    def _book_route(self, path: str):
        parts = path.strip("/").split("/"); book = self.app.library.books.get(parts[2] if len(parts) > 2 else "")
        if not book: return self._json(404, {"detail": "책을 찾을 수 없습니다"})
        action = parts[3] if len(parts) > 3 else ""
        if action == "manifest":
            chapters = [{
                "index": i,
                "url": f"{self.app.base_path}/api/books/{book.id}/resource/{urllib.parse.quote(href, safe='/')}",
                "audio": [{
                    "url": f"{self.app.base_path}/api/books/{book.id}/resource/{urllib.parse.quote(clip['member'], safe='/')}",
                    "begin": clip["begin"], "end": clip["end"], "target": clip["target"],
                } for clip in book.audio[i]],
            } for i, href in enumerate(book.spine)]
            return self._json(200, {**book.public(self.app.store.get(book.id), self.app.base_path), "chapters": chapters})
        if action == "progress": return self._json(200, self.app.store.get(book.id))
        if action == "cover" and book.cover: return self._resource(book, book.cover)
        if action == "download":
            return self._send_bytes(book.path.read_bytes(), "application/epub+zip", f"attachment; filename*=UTF-8''{urllib.parse.quote(book.path.name)}")
        if action == "resource" and len(parts) > 4: return self._resource(book, "/".join(parts[4:]))
        return self._json(404, {"detail": "자료를 찾을 수 없습니다"})

    def _resource(self, book: Book, member: str):
        try:
            member = _safe_member(member)
            with zipfile.ZipFile(book.path) as zf: data = zf.read(member)
        except (ValueError, KeyError, OSError, zipfile.BadZipFile): return self._json(404, {"detail": "EPUB 자료를 찾을 수 없습니다"})
        mime = mimetypes.guess_type(member)[0] or "application/octet-stream"
        extra = None
        if mime in {"application/xhtml+xml", "text/html"}:
            extra = "default-src 'none'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; media-src 'self'; font-src 'self';"
        return self._send_bytes(data, mime, csp=extra)

    def _send_bytes(self, data: bytes, mime: str, disposition: str | None = None, csp: str | None = None, cache_control: str = "private, max-age=3600"):
        self.send_response(200); self.send_header("Content-Type", mime); self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", cache_control); self.send_header("X-Content-Type-Options", "nosniff")
        if disposition: self.send_header("Content-Disposition", disposition)
        if csp: self.send_header("Content-Security-Policy", csp)
        self.end_headers(); self.wfile.write(data)

    def _static(self, path: str):
        name = "index.html" if path in {"/", ""} else path.lstrip("/")
        try: target = (STATIC_DIR / name).resolve(); target.relative_to(STATIC_DIR.resolve())
        except (ValueError, OSError): return self.send_error(404)
        if not target.is_file(): target = STATIC_DIR / "index.html"
        cache_control = "no-store" if target.name == "index.html" else "private, max-age=3600"
        return self._send_bytes(target.read_bytes(), mimetypes.guess_type(target.name)[0] or "application/octet-stream", cache_control=cache_control)


class App:
    def __init__(self, password: str, roots: list[Path]):
        self.password = password
        base = os.environ.get("JP_WEB_READER_BASE_PATH", "").strip("/")
        self.base_path = f"/{base}" if base else ""
        self.chatapp_db = Path(os.environ.get("JP_WEB_READER_CHATAPP_DB", "~/.tulpachat/chatapp.db")).expanduser()
        self.secret = load_secret(); self.library = Library(roots); self.store = Store(STATE_DIR / "reader.db")

    def valid_chat_owner_session(self, token: str) -> bool:
        """같은 호스트의 툴파챗 로그인 쿠키를 읽되 관리자 계정만 허용한다."""
        if not token or not self.chatapp_db.is_file():
            return False
        try:
            with sqlite3.connect(f"file:{self.chatapp_db}?mode=ro", uri=True, timeout=2) as db:
                row = db.execute(
                    "SELECT sessions.expires_at, users.is_owner FROM sessions "
                    "JOIN users ON users.id=sessions.user_id WHERE sessions.token=?",
                    (token,),
                ).fetchone()
            if not row or not bool(row[1]):
                return False
            expires = datetime.datetime.fromisoformat(row[0])
            now = datetime.datetime.now(datetime.timezone.utc)
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=datetime.timezone.utc)
            return expires >= now
        except (OSError, sqlite3.Error, TypeError, ValueError):
            return False


def main():
    parser = argparse.ArgumentParser(description="일본어 EPUB 비공개 웹 리더")
    parser.add_argument("--host", default=os.environ.get("JP_WEB_READER_HOST", "127.0.0.1")); parser.add_argument("--port", type=int, default=int(os.environ.get("JP_WEB_READER_PORT", "8766")))
    args = parser.parse_args(); password = os.environ.get("JP_WEB_READER_PASSWORD", "")
    if password and len(password) < 8: raise SystemExit("JP_WEB_READER_PASSWORD를 설정한다면 8자 이상이어야 합니다.")
    roots = [Path(os.environ.get("JP_EPUB_LIBRARY_DIR", DEFAULT_FINAL_DIR)), DEFAULT_FALLBACK_DIR]
    httpd = ThreadingHTTPServer((args.host, args.port), ReaderHandler); httpd.app = App(password, roots)  # type: ignore[attr-defined]
    print(f"일본어 EPUB 웹 서재: http://{args.host}:{args.port}{httpd.app.base_path}/ ({len(httpd.app.library.books)}권)")
    httpd.serve_forever()


if __name__ == "__main__": main()
